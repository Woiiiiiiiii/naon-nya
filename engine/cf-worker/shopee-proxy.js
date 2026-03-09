/**
 * Cloudflare Worker: Shopee Proxy
 * 
 * Routes requests from GitHub Actions through Cloudflare's IP
 * to bypass Shopee's IP blocking of data center IPs.
 * 
 * Deploy: CF Dashboard → Workers → Create Worker → paste this code
 * Set environment variable: PROXY_SECRET (same as CF_PROXY_KEY_API)
 * 
 * Usage from Python:
 *   POST https://<worker>.workers.dev/proxy
 *   Headers: X-Proxy-Key: <secret>
 *   Body JSON: { "url": "https://shopee.co.id/...", "method": "GET", 
 *                "headers": {...}, "cookies": "..." }
 */

export default {
  async fetch(request, env) {
    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'POST',
          'Access-Control-Allow-Headers': 'Content-Type, X-Proxy-Key',
        },
      });
    }

    // Only POST /proxy
    const url = new URL(request.url);
    if (request.method !== 'POST' || url.pathname !== '/proxy') {
      return new Response('Not Found', { status: 404 });
    }

    // Validate secret key
    const proxyKey = request.headers.get('X-Proxy-Key') || '';
    if (!proxyKey || proxyKey !== env.PROXY_SECRET) {
      return new Response('Unauthorized', { status: 401 });
    }

    try {
      const body = await request.json();
      const targetUrl = body.url;
      const method = (body.method || 'GET').toUpperCase();
      const targetHeaders = body.headers || {};
      const cookies = body.cookies || '';
      const postBody = body.body || null;

      if (!targetUrl || !targetUrl.startsWith('https://')) {
        return new Response('Invalid URL', { status: 400 });
      }

      // Build headers for Shopee request
      const fetchHeaders = new Headers();
      for (const [key, value] of Object.entries(targetHeaders)) {
        fetchHeaders.set(key, value);
      }

      // Add cookies if provided
      if (cookies) {
        fetchHeaders.set('Cookie', cookies);
      }

      // Add realistic browser headers if not present
      if (!fetchHeaders.has('User-Agent')) {
        fetchHeaders.set('User-Agent',
          'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/121.0.6167.101 Mobile Safari/537.36');
      }
      if (!fetchHeaders.has('Accept-Language')) {
        fetchHeaders.set('Accept-Language', 'id-ID,id;q=0.9,en;q=0.8');
      }

      // Make the proxied request
      const fetchOptions = {
        method: method,
        headers: fetchHeaders,
        redirect: 'follow',
      };
      if (postBody && method !== 'GET') {
        fetchOptions.body = JSON.stringify(postBody);
      }

      const response = await fetch(targetUrl, fetchOptions);

      // Determine content type
      const contentType = response.headers.get('Content-Type') || '';

      // For binary (images), return raw bytes
      if (contentType.startsWith('image/') || targetUrl.includes('susercontent.com')) {
        const imageData = await response.arrayBuffer();
        return new Response(imageData, {
          status: response.status,
          headers: {
            'Content-Type': contentType || 'application/octet-stream',
            'X-Proxy-Status': response.status.toString(),
            'Access-Control-Allow-Origin': '*',
          },
        });
      }

      // For JSON/text, return as-is
      const text = await response.text();
      return new Response(text, {
        status: response.status,
        headers: {
          'Content-Type': contentType || 'application/json',
          'X-Proxy-Status': response.status.toString(),
          'Access-Control-Allow-Origin': '*',
        },
      });

    } catch (err) {
      return new Response(JSON.stringify({ error: err.message }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      });
    }
  },
};
