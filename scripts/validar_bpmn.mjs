// Valida um .bpmn com o parser oficial do bpmn.io. Sai com código 1 se houver avisos.
//   cd scripts && npm install && node validar_bpmn.mjs ../exemplos/reembolso.bpmn
import { BpmnModdle } from 'bpmn-moddle';
import fs from 'fs';

const xml = fs.readFileSync(process.argv[2], 'utf8');
const { rootElement, warnings } = await new BpmnModdle().fromXML(xml);
console.log('OK root:', rootElement.$type, '| warnings:', warnings.length);
warnings.forEach(w => console.log(' -', w.message));
process.exit(warnings.length ? 1 : 0);
