import {test} from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync,sign} from 'node:crypto';
import {canonical,verifyReceipt} from './index.mjs';
test('offline verification separates authenticity, expiry and unknown lifecycle',()=>{
  const {privateKey,publicKey}=generateKeyPairSync('ed25519');
  const trust={test:publicKey.export({format:'der',type:'spki'}).subarray(-32).toString('base64url')};
  const protectedHeader={schema:'agent-evidence-receipt.1',algorithm:'Ed25519',key_id:'test'};
  const body={issued_at:'2026-01-01T00:00:00+00:00',expires_at:'2026-01-01T01:00:00+00:00',sample:true};
  const envelope={protected:protectedHeader,body,signature:sign(null,Buffer.concat([Buffer.from('8thGuard Agent Evidence Receipt v1\0'),Buffer.from(canonical({protected:protectedHeader,body}))]),privateKey).toString('base64url')};
  const valid=verifyReceipt(envelope,trust,{now:new Date('2026-01-01T00:30:00Z')});
  assert.equal(valid.integrity,true);assert.equal(valid.expired,false);assert.equal(valid.current_status,'unknown');assert.equal(valid.valid_current_receipt,false);
  assert.equal(verifyReceipt(envelope,{}).integrity,false);
  assert.equal(verifyReceipt(envelope,trust,{now:new Date('2026-01-01T02:00:00Z')}).expired,true);
  assert.equal(verifyReceipt({...envelope,body:{...body,sample:false}},trust).integrity,false);
});
