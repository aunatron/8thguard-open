const ERC8021_MARKER='80218021802180218021802180218021';
const CODE_PATTERN=/^[A-Za-z0-9_.-]+$/;

export function normalizeBuilderCodes(input) {
  const list=(Array.isArray(input)?input:String(input||'').split(','))
    .map(part=>part.trim())
    .filter(Boolean);
  if(list.length===0)throw new Error('Builder code cannot be empty');
  for(const code of list) {
    if(!CODE_PATTERN.test(code)) {
      throw new Error(`Invalid ERC-8021 builder code: ${code}`);
    }
  }
  return list;
}

export function encodeBuilderCodeSuffix(input) {
  const joined=normalizeBuilderCodes(input).join(',');
  const ascii=Buffer.from(joined,'ascii');
  if(ascii.length===0||ascii.length>255) {
    throw new Error('ERC-8021 builder code list must be 1 to 255 ASCII bytes');
  }
  const lenHex=ascii.length.toString(16).padStart(2,'0');
  return '0x'+ascii.toString('hex')+lenHex+'00'+ERC8021_MARKER;
}

export function appendBuilderCodeSuffix(hexData,input) {
  if(!/^0x[0-9a-fA-F]*$/.test(hexData)||hexData.length%2!==0) {
    throw new Error('Invalid hex calldata');
  }
  const suffix=encodeBuilderCodeSuffix(input);
  return hexData+suffix.slice(2);
}

export function decodeBuilderCodeSuffix(hexData) {
  if(!/^0x[0-9a-fA-F]*$/.test(hexData)||hexData.length%2!==0) {
    throw new Error('Invalid hex calldata');
  }
  const raw=hexData.slice(2).toLowerCase();
  const minTailLen=32+2+2; // 16-byte marker + 1-byte schemaId + 1-byte length
  if(raw.length<minTailLen||!raw.endsWith(ERC8021_MARKER)) {
    return {present:false,codes:[],baseData:hexData,suffix:null};
  }
  const schemaId=raw.slice(raw.length-34,raw.length-32);
  if(schemaId!=='00') {
    throw new Error(`Unsupported ERC-8021 schema ID: 0x${schemaId}`);
  }
  const byteLen=Number.parseInt(raw.slice(raw.length-36,raw.length-34),16);
  const totalSuffixHexLen=byteLen*2+36;
  if(byteLen===0||raw.length<totalSuffixHexLen) {
    throw new Error('Malformed ERC-8021 builder code suffix');
  }
  const codesStart=raw.length-totalSuffixHexLen;
  const codesAscii=Buffer.from(raw.slice(codesStart,raw.length-36),'hex').toString('ascii');
  const codes=normalizeBuilderCodes(codesAscii);
  return {
    present:true,
    schemaId:0,
    codes,
    baseData:'0x'+raw.slice(0,codesStart),
    suffix:'0x'+raw.slice(codesStart),
  };
}
