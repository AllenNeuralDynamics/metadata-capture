import type { NextApiRequest, NextApiResponse } from 'next';
import http from 'http';

export const config = {
  api: {
    bodyParser: true,
    responseLimit: false,
  },
};

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'POST') {
    res.status(405).end();
    return;
  }

  const postData = JSON.stringify(req.body);

  const proxyReq = http.request(
    {
      hostname: 'localhost',
      port: 8001,
      path: '/chat',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData),
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

      const padding = ': ' + ' '.repeat(2048) + '\n\n';
      res.write(padding);

      proxyRes.on('data', (chunk: Buffer) => {
        res.write(chunk);
        if (typeof (res as any).flush === 'function') {
          (res as any).flush();
        }
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
      res.status(502).json({ error: 'Backend unreachable' });
    }
  });

  proxyReq.write(postData);
  proxyReq.end();
}
