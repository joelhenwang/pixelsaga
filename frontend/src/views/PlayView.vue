<!-- Continue resolver (A07): role-aware entry. Players open the
  adventure; watcher, director, and deity open the world. Missing player
  binding surfaces repair instead of a silent first-character pick. -->
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ApiError, api } from "../api";
import { fail, headers } from "../store";

const route = useRoute();
const router = useRouter();
const message = ref("Opening your story.");

onMounted(async () => {
  const storyId = route.params.storyId as string;
  try {
    const detail = await api.readStory(storyId, headers.value);
    const grant = await api.roleGrant(detail.world_id, headers.value);
    const role = grant?.role ?? detail.mode ?? "watcher";
    if (role === "player") {
      if (!grant?.character_id) {
        fail("player unbound", new Error("bind a character before playing"));
        await router.replace("/stories");
        return;
      }
      await router.replace(`/stories/${storyId}/adventure`);
    } else {
      await router.replace(`/stories/${storyId}/world`);
    }
    await api.openStory(storyId, headers.value).catch(() => undefined);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      await router.replace("/stories");
      return;
    }
    fail("open failed", error);
    await router.replace("/stories");
  }
});
</script>
<template>
  <main class="page narrow">
    <p>{{ message }}</p>
  </main>
</template>
