import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn,execFileSync} from 'node:child_process';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createPublicClient,http} from 'viem';
import {appendBuilderCodeSuffix,decodeBuilderCodeSuffix,encodeBuilderCodeSuffix} from '../scripts/erc8021.mjs';

const rootDir=fileURLToPath(new URL('..',import.meta.url));
const anvilEntry=join(rootDir,'node_modules','@foundry-rs','anvil','bin.mjs');

async function waitForRpc(url,timeoutMs=10000) {
  const deadline=Date.now()+timeoutMs;
  while(Date.now()<deadline) {
    try {
      const res=await fetch(url,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'eth_chainId',params:[]})});
      if(res.ok)return;
    } catch {}
    await new Promise(r=>setTimeout(r,150));
  }
  throw new Error('Timed out waiting for local Anvil RPC');
}

test('ERC-8021 Schema 0 encoder matches Base official worked example and round-trips cleanly',()=>{
  const suffix=encodeBuilderCodeSuffix('baseapp');
  assert.equal(suffix,'0x62617365617070070080218021802180218021802180218021');
  const wrapped=appendBuilderCodeSuffix('0xdeadbeef','bc_8thguard');
  const decoded=decodeBuilderCodeSuffix(wrapped);
  assert.equal(decoded.present,true);
  assert.equal(decoded.schemaId,0);
  assert.deepEqual(decoded.codes,['bc_8thguard']);
  assert.equal(decoded.baseData,'0xdeadbeef');
});

test('operator.mjs and base-demo-deploy.mjs deploy and anchor with ERC-8021 Builder Code on chain 8453',async()=>{
  const port=8551;
  const rpc=`http://127.0.0.1:${port}`;
  const anvil=spawn(process.execPath,[anvilEntry,'--host','127.0.0.1','--port',String(port),'--chain-id','8453','--silent'],{
    cwd:rootDir,
    stdio:'ignore',
  });
  const tmp=mkdtempSync(join(tmpdir(),'8thguard-base-'));
  try {
    await waitForRpc(rpc);
    // Public disposable loopback key (same pattern as test/registry.test.mjs). Never reuse on public networks.
    const devKey='0x'+'1'.padStart(64,'0');
    const devAddr='0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf';
    await fetch(rpc,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:2,method:'anvil_setBalance',params:[devAddr,'0x3635c9adc5dea00000']})});

    const builderCode='bc_8thguard';
    const expectedSuffix=encodeBuilderCodeSuffix(builderCode);
    const client=createPublicClient({transport:http(rpc)});

    // 1. Test operator.mjs prepare + broadcast on base-mainnet (chain 8453) with ERC-8021 suffix
    const planPath=join(tmp,'base-deploy-plan.json');
    const manifestPath=join(tmp,'base-deploy-manifest.json');
    execFileSync(process.execPath,['scripts/operator.mjs','prepare','--network','base-mainnet','--operation','deploy','--builder-code',builderCode,'--out',planPath],{cwd:rootDir});
    const plan=JSON.parse(readFileSync(planPath,'utf8'));
    assert.equal(plan.network,'base-mainnet');
    assert.equal(plan.chain_id,8453);
    assert.equal(plan.builder_code,builderCode);
    assert.equal(plan.erc8021_suffix,expectedSuffix);
    assert.ok(plan.data.endsWith(expectedSuffix.slice(2)));

    execFileSync(process.execPath,['scripts/operator.mjs','broadcast','--broadcast','--local-test','--rpc',rpc,'--plan',planPath,'--out',manifestPath],{
      cwd:rootDir,
      env:{...process.env,REGISTRY_OPERATOR_PRIVATE_KEY:devKey},
    });
    const opManifest=JSON.parse(readFileSync(manifestPath,'utf8'));
    assert.equal(opManifest.chain_id,8453);
    assert.equal(opManifest.network,'local-base-simulation');
    assert.equal(opManifest.builder_code,builderCode);
    assert.match(opManifest.registry_address,/^0x[a-fA-F0-9]{40}$/);
    const opTx=await client.getTransaction({hash:opManifest.transaction_id});
    assert.ok(opTx.input.endsWith(expectedSuffix.slice(2)));

    // 2. Test base-demo-deploy.mjs dry-run + full broadcast with 3 attributed anchors
    const dryOut=execFileSync(process.execPath,['scripts/base-demo-deploy.mjs','--builder-code',builderCode],{cwd:rootDir,encoding:'utf8'});
    const dryPlan=JSON.parse(dryOut);
    assert.equal(dryPlan.chain_id,8453);
    assert.equal(dryPlan.broadcast,false);
    assert.equal(dryPlan.builder_code,builderCode);
    assert.equal(dryPlan.anchors.length,3);
    for(const a of dryPlan.anchors)assert.ok(a.calldata.endsWith(expectedSuffix.slice(2)));

    const demoManifestPath=join(tmp,'base-demo-manifest.json');
    execFileSync(process.execPath,['scripts/base-demo-deploy.mjs','--broadcast','--local-test','--rpc',rpc,'--builder-code',builderCode,'--out',demoManifestPath],{
      cwd:rootDir,
      env:{...process.env,REGISTRY_OPERATOR_PRIVATE_KEY:devKey},
    });
    const demoManifest=JSON.parse(readFileSync(demoManifestPath,'utf8'));
    assert.equal(demoManifest.chain_id,8453);
    assert.equal(demoManifest.builder_code,builderCode);
    assert.equal(demoManifest.synthetic_only,true);
    assert.equal(demoManifest.pii_included,false);
    assert.equal(demoManifest.anchors.length,3);
    assert.deepEqual(demoManifest.anchors.map(a=>a.fixture_id),['FN-001','FN-002','FN-004']);

    const deployTx=await client.getTransaction({hash:demoManifest.deploy_transaction_id});
    assert.ok(deployTx.input.endsWith(expectedSuffix.slice(2)));
    for(const a of demoManifest.anchors) {
      const tx=await client.getTransaction({hash:a.transaction_id});
      assert.ok(tx.input.endsWith(expectedSuffix.slice(2)));
    }
  } finally {
    anvil.kill();
    rmSync(tmp,{recursive:true,force:true});
  }
});
