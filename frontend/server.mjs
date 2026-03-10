import { createServer } from 'http';
import next from 'next';
import { WebSocketServer } from 'ws';

const dev = process.env.NODE_ENV !== 'production';
const hostname = '0.0.0.0';
const port = parseInt(process.env.PORT || '5000', 10);

const app = next({ dev, hostname, port });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  const server = createServer((req, res) => {
    handle(req, res);
  });

  const wss = new WebSocketServer({ noServer: true });

  server.on('upgrade', (req, socket, head) => {
    const pathname = new URL(req.url, `http://${req.headers.host}`).pathname;
    if (pathname === '/ws/chat') {
      wss.handleUpgrade(req, socket, head, (clientWs) => {
        let abortController = null;

        const pingInterval = setInterval(() => {
          if (clientWs.readyState === 1) {
            clientWs.ping();
          }
        }, 20000);

        clientWs.on('message', async (data) => {
          const payload = data.toString();
          abortController = new AbortController();

          try {
            const res = await fetch('http://localhost:8001/chat', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: payload,
              signal: abortController.signal,
            });

            if (!res.ok) {
              if (clientWs.readyState === 1) {
                clientWs.send(JSON.stringify({ error: `Backend error: ${res.status}` }));
                clientWs.close();
              }
              clearInterval(pingInterval);
              return;
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            const processLine = (line) => {
              if (line.startsWith('data: ')) {
                const eventData = line.slice(6);
                if (eventData === '[DONE]') {
                  if (clientWs.readyState === 1) {
                    clientWs.send(JSON.stringify({ done: true }));
                  }
                } else if (eventData.trim()) {
                  if (clientWs.readyState === 1) {
                    clientWs.send(eventData);
                  }
                }
              }
            };

            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              buffer += decoder.decode(value, { stream: true });
              const lines = buffer.split('\n');
              buffer = lines.pop() || '';

              for (const line of lines) {
                processLine(line);
              }
            }

            if (buffer.trim()) {
              processLine(buffer);
            }
          } catch (err) {
            if (err.name !== 'AbortError') {
              console.error('SSE-to-WS bridge error:', err.message);
              if (clientWs.readyState === 1) {
                clientWs.send(JSON.stringify({ error: err.message }));
              }
            }
          } finally {
            clearInterval(pingInterval);
            if (clientWs.readyState === 1) {
              clientWs.close();
            }
          }
        });

        clientWs.on('close', () => {
          clearInterval(pingInterval);
          if (abortController) abortController.abort();
        });

        clientWs.on('error', () => {
          clearInterval(pingInterval);
          if (abortController) abortController.abort();
        });
      });
    }
  });

  server.listen(port, hostname, () => {
    console.log(`> Custom server ready on http://${hostname}:${port}`);
  });
});
