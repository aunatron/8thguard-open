import {readFile,writeFile} from 'node:fs/promises';
import {createHash,generateKeyPairSync,randomBytes,sign} from 'node:crypto';
import {createPublicClient,createWalletClient,encodeFunctionData,formatEther,http,isAddress} from 'viem';
import {privateKeyToAccount} from 'viem/accounts';
import {canonical,envelopeHash,verifyReceipt} from '../../../packages/receipt-verifier/index.mjs';
import {appendBuilderCodeSuffix,encodeBuilderCodeSuffix} from './erc8021.mjs';

const BASE_CHAIN_ID=8453;
const DEFAULT_RPC='https://mainnet.base.org';
const BENCHMARKS=[
  {id:'FN-001',file:'../../../benchmarks/field-notes/FN-001-split-rail-finality.json'},
  {id:'FN-002',file:'../../../benchmarks/field-notes/FN-002-solana-ata-vs-owner.json'},
  {id:'FN-004',file:'../../../benchmarks/field-notes/FN-004-erc3643-rwa-freeze-and-identity-gap.json'},
];

const args=process.argv.slice(2);
const option=name=>{const i=args.indexOf(name);return i<0?undefined:args[i+1];};
const broadcast=args.includes('--broadcast');
const localTest=args.includes('--local-test');
const rpcUrl=option('--rpc')||DEFAULT_RPC;
const outPath=option('--out');
const existingRegistry=option('--registry');
const builderCode=option('--builder-code')||process.env.BASE_BUILDER_CODE||null;
const erc8021Suffix=builderCode?encodeBuilderCodeSuffix(builderCode):null;
const withAttribution=data=>builderCode?appendBuilderCodeSuffix(data,builderCode):data;

async function waitForRuntimeHash(client,address,expectedHash,attempts=8,delayMs=1500) {
  for(let i=0;i<attempts;i++) {
    const code=await client.getCode({address});
    const hash=createHash('sha256').update(Buffer.from((code||'0x').slice(2),'hex')).digest('hex');
    if(hash===expectedHash)return true;
    if(i+1<attempts)await new Promise(r=>setTimeout(r,delayMs));
  }
  return false;
}

async function waitForAnchoredEntry(client,registryAddress,abi,receiptRef,expectedDigest,attempts=8,delayMs=1500) {
  for(let i=0;i<attempts;i++) {
    const entry=await client.readContract({address:registryAddress,abi,functionName:'entries',args:[receiptRef]});
    if(entry[0].toLowerCase()===expectedDigest.toLowerCase()&&Number(entry[4])===1)return true;
    if(i+1<attempts)await new Promise(r=>setTimeout(r,delayMs));
  }
  return false;
}

const artifact=JSON.parse(await readFile(new URL('../artifacts/EvidenceRegistry.json',import.meta.url)));
const runtimeHash=createHash('sha256').update(Buffer.from(artifact.deployedBytecode.slice(2),'hex')).digest('hex');

const {privateKey,publicKey}=generateKeyPairSync('ed25519');
const keyId='base-synthetic-demo-v1';
const trust={[keyId]:publicKey.export({format:'der',type:'spki'}).subarray(-32).toString('base64url')};

const nowMs=Date.now();
const issuedIso=new Date(nowMs-60_000).toISOString();
const expiresUnix=BigInt(Math.floor(nowMs/1000)+12*3600);
const expiresIso=new Date(Number(expiresUnix)*1000).toISOString();

const items=[];
for(const b of BENCHMARKS) {
  const raw=await readFile(new URL(b.file,import.meta.url));
  const fixtureSha256=createHash('sha256').update(raw).digest('hex');
  const anchorRef=randomBytes(32).toString('hex');
  const protectedHeader={schema:'agent-evidence-receipt.1',algorithm:'Ed25519',key_id:keyId};
  const body={
    review_id:`synthetic-base-${b.id.toLowerCase()}`,
    issued_at:issuedIso,
    expires_at:expiresIso,
    anchor_reference:anchorRef,
    network:'base-mainnet',
    synthetic_benchmark_demo:true,
    fixture_id:b.id,
    fixture_sha256:fixtureSha256,
  };
  const payload=Buffer.concat([Buffer.from('8thGuard Agent Evidence Receipt v1\0'),Buffer.from(canonical({protected:protectedHeader,body}))]);
  const envelope={protected:protectedHeader,body,signature:sign(null,payload,privateKey).toString('base64url')};
  const check=verifyReceipt(envelope,trust,{now:new Date(nowMs)});
  if(!check.integrity||check.expired)throw new Error(`Synthetic receipt verification failed for ${b.id}`);
  const digest=envelopeHash(envelope);
  const rawCalldata=encodeFunctionData({
    abi:artifact.abi,
    functionName:'anchor',
    args:['0x'+anchorRef,'0x'+digest,expiresUnix],
  });
  items.push({
    fixture_id:b.id,
    fixture_sha256:fixtureSha256,
    receipt_ref:'0x'+anchorRef,
    digest:'0x'+digest,
    valid_until:Number(expiresUnix),
    expires_at:expiresIso,
    calldata:withAttribution(rawCalldata),
  });
}

if(!broadcast) {
  const plan={
    schema:'base-synthetic-anchor-plan.1',
    network:'base-mainnet',
    chain_id:BASE_CHAIN_ID,
    broadcast:false,
    builder_code:builderCode,
    erc8021_suffix:erc8021Suffix,
    source_sha256:artifact.sourceSha256,
    runtime_sha256:runtimeHash,
    synthetic_only:true,
    pii_included:false,
    anchors:items,
  };
  if(outPath)await writeFile(outPath,JSON.stringify(plan,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify(plan,null,2));
  process.exit(0);
}

const parsed=new URL(rpcUrl);
const isLoopback=localTest && parsed.hostname==='127.0.0.1' && parsed.protocol==='http:';
if(!isLoopback && (parsed.protocol!=='https:'||parsed.username||parsed.password)) {
  throw new Error('Secure HTTPS RPC required for Base Mainnet broadcast');
}
const rawKey=(process.env.REGISTRY_OPERATOR_PRIVATE_KEY||'').trim();
if(!/^0x[a-fA-F0-9]{64}$/.test(rawKey)) {
  throw new Error('Set REGISTRY_OPERATOR_PRIVATE_KEY (0x + 64 hex chars) in the current shell before running with --broadcast');
}

const publicClient=createPublicClient({transport:http(rpcUrl,{timeout:20000,retryCount:2})});
const liveChainId=await publicClient.getChainId();
if(liveChainId!==BASE_CHAIN_ID) {
  throw new Error(`RPC chain ID mismatch: expected ${BASE_CHAIN_ID} (base-mainnet), got ${liveChainId}`);
}

const account=privateKeyToAccount(rawKey);
const balance=await publicClient.getBalance({address:account.address});
if(balance===0n) {
  throw new Error(`Operator wallet ${account.address} has 0 ETH on chain ${BASE_CHAIN_ID}. Fund with a small amount of Base ETH for gas first.`);
}
const walletClient=createWalletClient({account,transport:http(rpcUrl,{timeout:20000,retryCount:2})});

let registryAddress=existingRegistry;
let deployTxHash=null;
let deployBlock=null;

if(registryAddress) {
  if(!isAddress(registryAddress))throw new Error('Invalid --registry address');
  if(!await waitForRuntimeHash(publicClient,registryAddress,runtimeHash,4,1500)) {
    throw new Error('Existing registry runtime SHA-256 mismatch');
  }
} else {
  const deployData=withAttribution(artifact.bytecode);
  deployTxHash=await walletClient.sendTransaction({chain:null,data:deployData,value:0n});
  console.error(JSON.stringify({step:'deploy_submitted',tx:deployTxHash,builder_code:builderCode}));
  const receipt=await publicClient.waitForTransactionReceipt({hash:deployTxHash,timeout:120000});
  if(receipt.status!=='success'||!receipt.contractAddress)throw new Error('Contract deployment failed');
  registryAddress=receipt.contractAddress;
  deployBlock=String(receipt.blockNumber);
  if(!await waitForRuntimeHash(publicClient,registryAddress,runtimeHash,8,1500)) {
    throw new Error('Deployed runtime SHA-256 mismatch');
  }
}

const anchored=[];
for(const item of items) {
  await publicClient.call({account,to:registryAddress,data:item.calldata,value:0n});
  const txHash=await walletClient.sendTransaction({chain:null,to:registryAddress,data:item.calldata,value:0n});
  console.error(JSON.stringify({step:'anchor_submitted',fixture_id:item.fixture_id,tx:txHash,builder_code:builderCode}));
  const mined=await publicClient.waitForTransactionReceipt({hash:txHash,timeout:120000});
  if(mined.status!=='success')throw new Error(`Anchor transaction failed for ${item.fixture_id}`);
  if(!await waitForAnchoredEntry(publicClient,registryAddress,artifact.abi,item.receipt_ref,item.digest,8,1500)) {
    throw new Error(`Onchain verification mismatch for ${item.fixture_id}`);
  }
  anchored.push({
    fixture_id:item.fixture_id,
    fixture_sha256:item.fixture_sha256,
    receipt_ref:item.receipt_ref,
    digest:item.digest,
    valid_until:item.valid_until,
    transaction_id:txHash,
    block_number:String(mined.blockNumber),
    basescan_tx:isLoopback?null:`https://basescan.org/tx/${txHash}`,
  });
}

const manifest={
  schema:'base-registry-deployment-manifest.1',
  network:isLoopback?'local-base-simulation':'base-mainnet',
  chain_id:BASE_CHAIN_ID,
  publisher:account.address,
  operator_balance_before_eth:formatEther(balance),
  builder_code:builderCode,
  erc8021_suffix:erc8021Suffix,
  registry_address:registryAddress,
  basescan_contract:isLoopback?null:`https://basescan.org/address/${registryAddress}`,
  deploy_transaction_id:deployTxHash,
  deploy_basescan_tx:(!isLoopback && deployTxHash)?`https://basescan.org/tx/${deployTxHash}`:null,
  deploy_block_number:deployBlock,
  runtime_sha256:runtimeHash,
  source_sha256:artifact.sourceSha256,
  synthetic_only:true,
  pii_included:false,
  anchors:anchored,
};

if(outPath)await writeFile(outPath,JSON.stringify(manifest,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(manifest,null,2));
