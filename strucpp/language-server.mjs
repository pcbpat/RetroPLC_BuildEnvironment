import { EventEmitter } from 'node:events';
const events = new EventEmitter();
// Reserve stdout for LSP messages.
console.log = console.info = console.warn = (...args) => console.error(...args);
globalThis.self = {
  addEventListener(type, listener) { events.on(type, listener); },
  removeEventListener(type, listener) { events.off(type, listener); },
  postMessage(message) {
    const body = Buffer.from(JSON.stringify(message), 'utf8');
    process.stdout.write(Buffer.concat([Buffer.from(`Content-Length: ${body.length}\r\n\r\n`), body]));
  }
};
await import('strucpp/dist/browser-server.js');
let buffer = Buffer.alloc(0);
process.stdin.on('data', chunk => {
  buffer = Buffer.concat([buffer, chunk]);
  while (true) {
    const end = buffer.indexOf('\r\n\r\n');
    if (end === -1) return;
    const match = buffer.subarray(0,end).toString('ascii').match(/^Content-Length:\s*(\d+)\s*$/im);
    if (!match) throw new Error('Invalid LSP header');
    const length = Number(match[1]);
    const start = end + 4;
    if (buffer.length < start + length) return;
    const message = JSON.parse(buffer.subarray(start,start+length).toString('utf8'));
    buffer = buffer.subarray(start+length);
    globalThis.self.onmessage({data: message});
    if (message.method === 'exit') process.exitCode = 0;
  }
});
process.stdin.on('end', () => process.exit(0));
