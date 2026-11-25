import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {createPublicClient,createWalletClient,decodeFunctionData,encodeFunctionData,http,isAddress} from 'viem';
import {privateKeyToAccount} from 'viem/accounts';
import {verifyReceipt,envelopeHash} from '../../../packages/receipt-verifier/index.mjs';

const NETWORKS={
  'xdc-apothem':{chainId:51,rpc:'https://rpc.apothem.network',localName:'local-apothem-simulation'},
  'celo-mainnet':{chainId:42220,rpc:'https://forno.celo.org',localName:'local-celo-simulation'},
};
const args=process.argv.slice(2),command=args.shift();
const option=name=>{const i=args.indexOf(name);return i<0?undefined:args[i+1];};
const resolveNetwork=name=>{const key=name||'xdc-apothem';if(!Object.hasOwn(NETWORKS,key))throw new Error('Unsupported network; use xdc-apothem or celo-mainnet');return {name:key,...NETWORKS[key]};};
const read=async file=>{if(!file)throw new Error('Required input file missing');const bytes=await readFile(file);if(bytes.length>100000)throw new Error('Input exceeds limit');return JSON.parse(bytes);};
const artifact=JSON.parse(await readFile(new URL('../artifacts/EvidenceRegistry.json',import.meta.url)));
const runtimeHash=createHash('sha256').update(Buffer.from(artifact.deployedBytecode.slice(2),'hex')).digest('hex');
let plan;
if(command==='prepare') {
  const net=resolveNetwork(option('--network'));
  const operation=option('--operation')||'anchor';
  if(operation==='deploy')plan={schema:'registry-transaction-plan.1',network:net.name,operation,chain_id:net.chainId,data:artifact.bytecode,value:'0',source_sha256:artifact.sourceSha256,runtime_sha256:runtimeHash};
  else {
    const registry=option('--registry');if(!isAddress(registry))throw new Error('A registry address is required');
    const envelope=await read(option('--receipt')),trust=await read(option('--trust'));
    const verified=verifyReceipt(envelope,trust);
    if(!verified.integrity||(operation==='anchor'&&verified.expired))throw new Error('Receipt must be authentic and independently trusted; new anchors must be unexpired');
    const ref=envelope.body.anchor_reference;
    if(!/^[a-f0-9]{64}$/.test(ref))throw new Error('Invalid opaque receipt reference');
    let functionName,values;
    if(operation==='anchor') {
      functionName='anchor';values=['0x'+ref,'0x'+envelopeHash(envelope),BigInt(Math.floor(Date.parse(envelope.body.expires_at)/1000))];
    } else if(operation==='withdraw') {functionName='withdraw';values=['0x'+ref];}
    else if(operation==='supersede') {
      const replacement=await read(option('--replacement'));
      const check=verifyReceipt(replacement,trust);
      if(!check.integrity||check.expired||!/^[a-f0-9]{64}$/.test(replacement.body.anchor_reference)||replacement.body.review_id!==envelope.body.review_id)throw new Error('Replacement must be a current receipt for the same review');
      functionName='supersede';values=['0x'+ref,'0x'+replacement.body.anchor_reference];
    } else throw new Error('Unsupported operation');
    plan={schema:'registry-transaction-plan.1',network:net.name,operation,chain_id:net.chainId,to:registry,data:encodeFunctionData({abi:artifact.abi,functionName,args:values}),value:'0',runtime_sha256:runtimeHash,source_sha256:artifact.sourceSha256,receipt_hash:envelopeHash(envelope),receipt_ref:ref,service_lifecycle:'must_be_checked_separately'};
  }
  if(!option('--out'))throw new Error('Use --out to save a reviewable unsigned transaction plan');
  await writeFile(option('--out'),JSON.stringify(plan,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({prepared:true,network:net.name,operation:plan.operation,chain_id:net.chainId,output:option('--out'),broadcast:false}));
} else if(command==='broadcast') {
  if(!args.includes('--broadcast'))throw new Error('Explicit --broadcast required after reviewing the plan');
  plan=await read(option('--plan'));
  const net=resolveNetwork(option('--network')||plan.network||'xdc-apothem');
  const url=option('--rpc')||net.rpc,parsed=new URL(url);
  const local=args.includes('--local-test') && parsed.hostname==='127.0.0.1' && parsed.protocol==='http:';
  if(!local && (parsed.protocol!=='https:'||parsed.username||parsed.password))throw new Error(`Secure HTTPS RPC required for ${net.name}`);
  if(plan.chain_id!==net.chainId||plan.value!=='0'||plan.schema!=='registry-transaction-plan.1'||plan.runtime_sha256!==runtimeHash||plan.source_sha256!==artifact.sourceSha256)throw new Error('Unrecognised plan or artifact');
  const source=createPublicClient({transport:http(url,{timeout:10000,retryCount:0})});
  if(await source.getChainId()!==net.chainId)throw new Error(`RPC chain ID mismatch: expected ${net.chainId} (${net.name})`);
  const account=privateKeyToAccount(process.env.REGISTRY_OPERATOR_PRIVATE_KEY||'');
  const wallet=createWalletClient({account,transport:http(url)});
  const deployment=plan.operation==='deploy';
  if(deployment && plan.data!==artifact.bytecode)throw new Error('Deployment bytecode mismatch');
  if(!deployment) {
    if(!['anchor','withdraw','supersede'].includes(plan.operation)||!isAddress(plan.to))throw new Error('Invalid operation');
    const decoded=decodeFunctionData({abi:artifact.abi,data:plan.data});
    if(decoded.functionName!==plan.operation||decoded.args[0]!=='0x'+plan.receipt_ref)throw new Error('Plan operation does not match its calldata');
    if(plan.operation==='anchor' && decoded.args[1]!=='0x'+plan.receipt_hash)throw new Error('Plan receipt hash does not match its calldata');
    const code=await source.getCode({address:plan.to});
    if(createHash('sha256').update(Buffer.from((code||'0x').slice(2),'hex')).digest('hex')!==runtimeHash)throw new Error('Registry runtime mismatch');
    if(!await source.readContract({address:plan.to,abi:artifact.abi,functionName:'publishers',args:[account.address]}))throw new Error('Operator is not an allowed publisher');
    // Simulate the exact plan, then submit it unchanged. The chain remains the lifecycle authority.
    await source.call({account,to:plan.to,data:plan.data,value:0n});
  }
  const hash=await wallet.sendTransaction({chain:null,...(!deployment?{to:plan.to}:{}),data:plan.data,value:0n});
  // Print the public transaction reference immediately so interrupted polling can be resumed.
  console.log(JSON.stringify({submitted:true,network:net.name,chain_id:net.chainId,operation:plan.operation,transaction_id:hash}));
  const mined=await source.waitForTransactionReceipt({hash,timeout:120000});
  if(mined.status!=='success')throw new Error('Transaction failed');
  const address=mined.contractAddress||plan.to;
  const code=await source.getCode({address});
  if(createHash('sha256').update(Buffer.from((code||'0x').slice(2),'hex')).digest('hex')!==runtimeHash)throw new Error('Deployed runtime mismatch');
  const manifest={schema:'registry-deployment.1',network:local?net.localName:net.name,chain_id:net.chainId,operation:plan.operation,registry_address:address,publisher:account.address,transaction_id:hash,block_number:String(mined.blockNumber),runtime_sha256:runtimeHash,source_sha256:artifact.sourceSha256,confirmation:'mined; further confirmation required'};
  if(option('--out'))await writeFile(option('--out'),JSON.stringify(manifest,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify(manifest));
} else throw new Error('Use prepare or broadcast; see README.md');
