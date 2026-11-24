import {createHash, createPublicKey, verify as verifySignature} from 'node:crypto';
const domain=Buffer.from('8thGuard Agent Evidence Receipt v1\0');
export function canonical(value, depth=0) {
  if(depth>20) throw new Error('Receipt nesting exceeds limit');
  if(value===null || typeof value==='boolean')return JSON.stringify(value);
  if(typeof value==='string') { if(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value))throw new Error('Invalid Unicode');return JSON.stringify(value); }
  if(typeof value==='number' && Number.isSafeInteger(value) && !Object.is(value,-0))return String(value);
  if(Array.isArray(value))return '['+value.map(v=>canonical(v,depth+1)).join(',')+']';
  if(value && typeof value==='object' && Object.getPrototypeOf(value)===Object.prototype) {
    const keys=Object.keys(value).sort();
    if(keys.some(k=>!/^[\x20-\x7e]+$/.test(k)))throw new Error('Unsupported field name');
    return '{'+keys.map(k=>JSON.stringify(k)+':'+canonical(value[k],depth+1)).join(',')+'}';
  }
  throw new Error('Unsupported receipt value');
}
export function envelopeHash(envelope) {return createHash('sha256').update(canonical(envelope)).digest('hex');}
function decode(value,length) {
  if(typeof value!=='string'||!/^[A-Za-z0-9_-]+$/.test(value))throw new Error('Invalid encoding');
  const bytes=Buffer.from(value,'base64url');
  if(bytes.length!==length || bytes.toString('base64url')!==value)throw new Error('Invalid encoding');
  return bytes;
}
export function verifyReceipt(envelope, trustedKeys, {now=new Date()}={}) {
  const result={integrity:false,trusted_publisher:false,expired:null,current_status:'unknown',status_checked:false,valid_current_receipt:false};
  try {
    if(Object.keys(envelope).sort().join(',')!=='body,protected,signature'||Buffer.byteLength(canonical(envelope))>60000)throw new Error('Invalid envelope');
    const {protected:header,body}=envelope;
    if(Object.keys(header).sort().join(',')!=='algorithm,key_id,schema'||header.algorithm!=='Ed25519'||header.schema!=='agent-evidence-receipt.1')throw new Error('Unsupported receipt');
    if(!Object.hasOwn(trustedKeys,header.key_id))throw new Error('Publisher not independently pinned');
    const publicBytes=decode(trustedKeys[header.key_id],32);
    const key=createPublicKey({key:Buffer.concat([Buffer.from('302a300506032b6570032100','hex'),publicBytes]),format:'der',type:'spki'});
    result.trusted_publisher=true;
    if(!verifySignature(null,Buffer.concat([domain,Buffer.from(canonical({protected:header,body}))]),key,decode(envelope.signature,64)))throw new Error('Invalid signature');
    const issued=Date.parse(body.issued_at),expires=Date.parse(body.expires_at);
    const aware=v=>typeof v==='string' && /(?:Z|[+-]\d\d:\d\d)$/.test(v);
    if(!aware(body.issued_at)||!aware(body.expires_at)||!Number.isFinite(issued)||!Number.isFinite(expires)||issued>now.getTime()||expires<=issued)throw new Error('Invalid validity interval');
    result.expired=expires<=now.getTime();result.integrity=true;
  } catch { /* Deliberately return an unknown lifecycle; offline content cannot establish it. */ }
  return result;
}
