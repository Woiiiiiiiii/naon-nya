"""
Freesound API diagnostic — runs in GitHub Actions where FREESOUND_API_KEY is available.
Tests: search, download preview, validate audio.
Prints FULL diagnostic so we can see in Actions logs.
"""
import os, sys, requests, time

api_key = os.environ.get('FREESOUND_API_KEY', '')
print("=" * 60)
print("FREESOUND API DIAGNOSTIC")
print("=" * 60)

if not api_key:
    print("[SKIP] FREESOUND_API_KEY not set — this test must run in GitHub Actions")
    sys.exit(0)

print(f"API Key: {api_key[:4]}...{api_key[-4:]}")

# Test 1: Basic search (wide query, no tag filter)
print("\n--- Test 1: Wide search (no tag filter) ---")
url = "https://freesound.org/apiv2/search/text/"
params = {
    'query': 'music background',
    'filter': 'duration:[15 TO 300]',
    'fields': 'id,name,previews,duration,tags,type',
    'page_size': 5,
    'sort': 'rating_desc',
    'token': api_key,
}
try:
    resp = requests.get(url, params=params, timeout=30)
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"  Total: {data.get('count', 0)} results")
        for s in data.get('results', []):
            prev = s.get('previews', {})
            has_mp3 = bool(prev.get('preview-hq-mp3') or prev.get('preview-lq-mp3'))
            print(f"  [{s['id']}] {s.get('name','?')[:40]} ({s.get('duration',0):.0f}s) type={s.get('type','')} preview={has_mp3}")
    else:
        print(f"  Body: {resp.text[:300]}")
except Exception as e:
    print(f"  ERROR: {e}")

# Test 2: Category-specific search (same query as code uses)
queries = {
    'home': 'cheerful acoustic happy ukulele',
    'fashion': 'upbeat pop background music',
    'beauty': 'soft elegant piano ambient',
}
for cat, query in queries.items():
    print(f"\n--- Test 2: Category search [{cat}]: '{query}' ---")
    params2 = {
        'query': query,
        'filter': 'duration:[30 TO 300] tag:music',
        'fields': 'id,name,previews,duration',
        'page_size': 3,
        'sort': 'rating_desc',
        'token': api_key,
    }
    try:
        resp = requests.get(url, params=params2, timeout=30)
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            count = data.get('count', 0)
            results = data.get('results', [])
            print(f"  Total: {count} results, returned: {len(results)}")
            if count == 0:
                # Try WITHOUT tag:music filter
                print("  Retrying WITHOUT tag:music filter...")
                params2['filter'] = 'duration:[15 TO 300]'
                resp2 = requests.get(url, params=params2, timeout=30)
                if resp2.status_code == 200:
                    data2 = resp2.json()
                    print(f"  Without tag filter: {data2.get('count', 0)} results")
        else:
            print(f"  Body: {resp.text[:200]}")
    except Exception as e:
        print(f"  ERROR: {e}")

# Test 3: Download a preview
print("\n--- Test 3: Download preview ---")
params3 = {
    'query': 'background music',
    'filter': 'duration:[15 TO 120]',
    'fields': 'id,name,previews,duration',
    'page_size': 1,
    'sort': 'rating_desc',
    'token': api_key,
}
try:
    resp = requests.get(url, params=params3, timeout=30)
    if resp.status_code == 200:
        results = resp.json().get('results', [])
        if results:
            prev = results[0].get('previews', {})
            mp3_url = prev.get('preview-hq-mp3') or prev.get('preview-lq-mp3', '')
            if mp3_url:
                print(f"  URL: {mp3_url[:80]}...")
                audio = requests.get(mp3_url, timeout=20)
                print(f"  Status: {audio.status_code}")
                print(f"  Size: {len(audio.content)} bytes")
                magic = audio.content[:4]
                is_mp3 = magic[:3] == b'ID3' or magic[:2] in (b'\xff\xfb', b'\xff\xf3')
                print(f"  Magic: {magic.hex()} — {'VALID MP3' if is_mp3 else 'NOT MP3'}")
            else:
                print("  No preview URL available")
        else:
            print("  No results")
    else:
        print(f"  Error: {resp.status_code} {resp.text[:200]}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
