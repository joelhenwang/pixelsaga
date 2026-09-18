// Asset object-URL cache (P04).
//
// Production art loads through authenticated fetch, never plain img src
// (the bearer header cannot ride a raw URL). Object URLs are cached by
// immutable asset id and revoked when replaced. Failures fall back to
// the deterministic pixel fixture so narrative and map stay usable.
import { api } from "./api";
import { portraitFor as fixturePortrait } from "./portrait";

const urls = new Map<string, string>();

export async function assetUrl(
  assetId: string,
  worldId: string,
  headers: Record<string, string>,
  fallbackName: string,
): Promise<string> {
  const cached = urls.get(assetId);
  if (cached !== undefined) {
    return cached;
  }
  try {
    const blob = await api.assetBytes(assetId, worldId, headers);
    const url = URL.createObjectURL(blob);
    urls.set(assetId, url);
    return url;
  } catch {
    return fixturePortrait(assetId, fallbackName);
  }
}

export function revokeAssetUrl(assetId: string): void {
  const cached = urls.get(assetId);
  if (cached !== undefined) {
    URL.revokeObjectURL(cached);
    urls.delete(assetId);
  }
}

export function clearAssetCache(): void {
  for (const url of urls.values()) {
    URL.revokeObjectURL(url);
  }
  urls.clear();
}
