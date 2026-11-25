import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn,execFileSync} from 'node:child_process';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

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

test('operator.mjs and celo-demo-deploy.mjs deploy and anchor 3 synthetic benchmarks on chain 42220',async()=>{
  const port=8550;
  const rpc=`http://127.0.0.1:${port}`;
  const anvil=spawn(process.execPath,[anvilEntry,'--host','127.0.0.1','--port',String(port),'--chain-id','42220','--silent'],{
    cwd:rootDir,
    stdio:'ignore',
  });
  const tmp=mkdtempSync(join(tmpdir(),'8thguard-celo-'));
  try {
    await waitForRpc(rpc);
    // Public disposable loopback key (same pattern as test/registry.test.mjs). Never reuse on public networks.
    const devKey='0x'+'1'.padStart(64,'0');
    const devAddr='0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf';
    await fetch(rpc,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:2,method:'anvil_setBalance',params:[devAddr,'0x3635c9adc5dea00000']})});

    // 1. Test operator.mjs prepare + broadcast on celo-mainnet (chain 42220)
    const planPath=join(tmp,'deploy-plan.json');
    const manifestPath=join(tmp,'deploy-manifest.json');
    execFileSync(process.execPath,['scripts/operator.mjs','prepare','--network','celo-mainnet','--operation','deploy','--out',planPath],{cwd:rootDir});
    const plan=JSON.parse(readFileSync(planPath,'utf8'));
    assert.equal(plan.network,'celo-mainnet');
    assert.equal(plan.chain_id,42220);

    execFileSync(process.execPath,['scripts/operator.mjs','broadcast','--broadcast','--local-test','--rpc',rpc,'--plan',planPath,'--out',manifestPath],{
      cwd:rootDir,
      env:{...process.env,REGISTRY_OPERATOR_PRIVATE_KEY:devKey},
    });
    const opManifest=JSON.parse(readFileSync(manifestPath,'utf8'));
    assert.equal(opManifest.chain_id,42220);
    assert.equal(opManifest.network,'local-celo-simulation');
    assert.match(opManifest.registry_address,/^0x[a-fA-F0-9]{40}$/);

    // 2. Test celo-demo-deploy.mjs dry-run (no private key) and full broadcast + 3 anchors
    const dryOut=execFileSync(process.execPath,['scripts/celo-demo-deploy.mjs'],{cwd:rootDir,encoding:'utf8'});
    const dryPlan=JSON.parse(dryOut);
    assert.equal(dryPlan.chain_id,42220);
    assert.equal(dryPlan.broadcast,false);
    assert.equal(dryPlan.anchors.length,3);

    const demoManifestPath=join(tmp,'celo-demo-manifest.json');
    execFileSync(process.execPath,['scripts/celo-demo-deploy.mjs','--broadcast','--local-test','--rpc',rpc,'--out',demoManifestPath],{
      cwd:rootDir,
      env:{...process.env,REGISTRY_OPERATOR_PRIVATE_KEY:devKey},
    });
    const demoManifest=JSON.parse(readFileSync(demoManifestPath,'utf8'));
    assert.equal(demoManifest.chain_id,42220);
    assert.equal(demoManifest.synthetic_only,true);
    assert.equal(demoManifest.pii_included,false);
    assert.equal(demoManifest.anchors.length,3);
    assert.deepEqual(demoManifest.anchors.map(a=>a.fixture_id),['FN-001','FN-002','FN-004']);
  } finally {
    anvil.kill();
    rmSync(tmp,{recursive:true,force:true});
  }
});
