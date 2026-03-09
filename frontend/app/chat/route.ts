export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  const body = await req.text();

  const backendRes = await fetch('http://localhost:8001/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });

  if (!backendRes.ok) {
    return new Response(backendRes.statusText, { status: backendRes.status });
  }

  if (!backendRes.body) {
    return new Response('No response body', { status: 502 });
  }

  const encoder = new TextEncoder();
  const reader = backendRes.body.getReader();

  const stream = new ReadableStream({
    start(controller) {
      const padding = ': ' + ' '.repeat(2048) + '\n\n';
      controller.enqueue(encoder.encode(padding));

      (async () => {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              controller.close();
              break;
            }
            controller.enqueue(value);
          }
        } catch (err) {
          controller.error(err);
        }
      })();
    },
    cancel() {
      reader.cancel();
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-store, no-transform',
      'X-Accel-Buffering': 'no',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}
