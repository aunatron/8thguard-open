import {readFile} from 'node:fs/promises';
import {verifyReceipt,envelopeHash} from './index.mjs';
const [receiptFile,trustFile]=process.argv.slice(2);
if(!receiptFile||!trustFile)throw new Error('Usage: node cli.mjs receipt.json independently-pinned-keys.json');
const read=async path=>{const data=await readFile(path);if(data.length>60000)throw new Error('File exceeds limit');return JSON.parse(data);};
const receipt=await read(receiptFile),trust=await read(trustFile);
const result=verifyReceipt(receipt,trust);
console.log(JSON.stringify({...result,envelope_hash:result.integrity?envelopeHash(receipt):null}));
if(!result.integrity||result.expired)process.exitCode=1;
