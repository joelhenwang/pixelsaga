<!-- Legacy route compatibility (A07): old gameplay bookmarks resolve
  to an explicit story. Exactly one story redirects; many asks; none
  routes to the catalog. Never silently picks array index zero. -->
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api";
import { fail, headers } from "../store";
import { isStoryId, lastStoryHint } from "../composables/useStoryContext";

const route = useRoute();
const router = useRouter();
const message = ref("Resolving your story.");

function targetFor(storyId: string): string {
  const tail = route.path === "/scene" || route.path === "/adventure" ? "adventure"
    : route.path === "/map" || route.path === "/world" ? "world"
    : route.path === "/party" ? "party"
    : route.path === "/timeline" ? "journal"
    : route.path === "/diary" ? "diary"
    : route.path === "/relations" ? "relations"
    : route.path === "/generations" ? "eras"
    : route.path === "/operations" ? "operations"
    : "adventure";
  return `/stories/${storyId}/${tail}`;
}

onMounted(async () => {
  let controller: AbortController | null = new AbortController();
  try {
    const page = await api.listStories(
      headers.value, { status: "all", limit: 100 }, { signal: controller.signal },
    );
    const items = (page.items ?? []).filter((s) => !s.archived);
    if (!items.length) {
      await router.replace("/stories");
      return;
    }
    if (items.length === 1 && items[0]) {
      await router.replace(targetFor(items[0].story_id));
      return;
    }
    const hint = lastStoryHint();
    if (hint && isStoryId(hint) && items.some((s) => s.story_id === hint)) {
      await router.replace(targetFor(hint));
      return;
    }
    fail("several stories exist", new Error("pick one in Stories"));
    await router.replace("/stories");
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return;
    fail("resolve failed", error);
    await router.replace("/stories");
  } finally {
    controller = null;
  }
});
</script>
<template>
  <main class="page narrow">
    <p>{{ message }}</p>
  </main>
</template>
