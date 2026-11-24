import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createPublicClient,createWalletClient,http,parseEther,zeroAddress} from 'viem';
import {privateKeyToAccount} from 'viem/accounts';

test('commitments, idempotency, authorisation and lifecycle on a real local EVM',async t=>{
  const url=process.env.LOCAL_EVM_URL||'http://127.0.0.1:8549';
  if(new URL(url).hostname!=='127.0.0.1')throw new Error('Tests require the disposable loopback chain');
  const publicClient=createPublicClient({transport:http(url)});
  assert.equal(await publicClient.getChainId(),51);
  // Public, disposable development accounts. Never use these on a public network.
  const account=privateKeyToAccount('0x'+'1'.padStart(64,'0'));
  const other=privateKeyToAccount('0x'+'2'.padStart(64,'0'));
  await publicClient.request({method:'anvil_setBalance',params:[account.address,'0x3635c9adc5dea00000']});
  await publicClient.request({method:'anvil_setBalance',params:[other.address,'0x3635c9adc5dea00000']});
  const wallet=createWalletClient({account,transport:http(url)});
  const artifact=JSON.parse(await readFile(new URL('../artifacts/EvidenceRegistry.json',import.meta.url)));
  const deployed=await publicClient.waitForTransactionReceipt({hash:await wallet.deployContract({...artifact,chain:null})});
  const address=deployed.contractAddress,abi=artifact.abi;
  const read=(functionName,args=[])=>publicClient.readContract({address,abi,functionName,args});
  const write=async(functionName,args=[])=>{
    const {request}=await publicClient.simulateContract({address,abi,functionName,args,account});
    return publicClient.waitForTransactionReceipt({hash:await wallet.writeContract({...request,chain:null})});
  };
  const reject=(functionName,args=[],actor=account)=>assert.rejects(()=>publicClient.simulateContract({address,abi,functionName,args,account:actor}));
  const ref='0x'+'11'.repeat(32),ref2='0x'+'22'.repeat(32),digest='0x'+'33'.repeat(32),zero='0x'+'00'.repeat(32);
  const now=(await publicClient.getBlock()).timestamp,expiry=now+3600n;
  await t.test('only publishers may anchor and invalid commitments expire safely',async()=>{
    await reject('anchor',[ref,digest,expiry],other);
    await reject('anchor',[zero,digest,expiry]);await reject('anchor',[ref,zero,expiry]);
    await reject('anchor',[ref,digest,now]);await reject('anchor',[ref,digest,now+86410n]);
    await reject('setPublisher',[zeroAddress,true]);
    const receipt=await write('anchor',[ref,digest,expiry]);assert.equal(receipt.status,'success');
    assert.equal((await read('entries',[ref]))[0],digest);
    assert.equal((await write('anchor',[ref,digest,expiry])).logs.length,0);
    await reject('anchor',[ref,ref2,expiry]);
    await assert.rejects(()=>publicClient.estimateGas({account,to:address,value:parseEther('1')}));
  });
  await t.test('superseding and withdrawal preserve immutable commitments',async()=>{
    await write('anchor',[ref2,digest,expiry]);
    await reject('supersede',[ref,ref]);await reject('withdraw',[ref],other);
    await write('supersede',[ref,ref2]);assert.equal((await read('entries',[ref]))[4],3);
    await reject('anchor',[ref,digest,expiry]);
    await write('withdraw',[ref2]);assert.equal((await read('entries',[ref2]))[4],2);
    assert.equal((await write('withdraw',[ref2])).logs.length,0);
  });
  await t.test('owner handover requires acceptance by the proposed address',async()=>{
    await write('proposeOwner',[other.address]);await reject('acceptOwnership');
    const second=createWalletClient({account:other,transport:http(url)});
    await publicClient.waitForTransactionReceipt({hash:await second.writeContract({address,abi,functionName:'acceptOwnership',chain:null})});
    assert.equal((await read('owner')).toLowerCase(),other.address.toLowerCase());
    await reject('setPublisher',[account.address,false]);
  });
});
