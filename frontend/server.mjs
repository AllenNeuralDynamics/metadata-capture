import { createServer } from 'http';
import next from 'next';
import { request as httpRequest } from 'http';

const dev = process.env.NODE_ENV !== 'production';
const hostname = '0.0.0.0';
const port = parseInt(process.env.PORT || '5000', 10);

const app = next({ dev, hostname, port });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/api/chat') {
      let body = '';
      req.on('data', (chunk) => { body += chunk; });
      req.on('end', () => {
        const proxyReq = httpRequest(
          {
            hostname: 'localhost',
            port: 8001,
            path: '/chat',
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Content-Length': Buffer.byteLength(body),
            },
          },
          (proxyRes) => {
            res.writeHead(200, {
              'Content-Type': 'text/event-stream',
              'Cache-Control': 'no-cache, no-store, no-transform',
              'X-Accel-Buffering': 'no',
              'X-Content-Type-Options': 'nosniff',
              Connection: 'keep-alive',
            });

            proxyRes.on('data', (chunk) => {
              res.write(chunk);
            });

            proxyRes.on('end', () => {
              res.end();
            });

            proxyRes.on('error', () => {
              res.end();
            });
          },
        );

        proxyReq.on('error', () => {
          if (!res.headersSent) {
            res.writeHead(502, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Backend unreachable' }));
          }
        });

        proxyReq.write(body);
        proxyReq.end();
      });
    } else {
      handle(req, res);
    }
  }).listen(port, hostname, () => {
    console.log(`> Custom server ready on http://${hostname}:${port}`);
  });
});
