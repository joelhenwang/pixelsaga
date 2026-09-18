<!-- Story shell (A07): compact gameplay nav, current story name, safe
  link back to Stories, current clock. One design system, no second
  full navbar. Story entry validates and binds context; leaving voids it. -->
<script setup lang="ts">
import { onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ApiError } from "../api";
import { clock, connection, fail, notice, worldStatus } from "../store";
import { currentStory, enterStory, leaveStory } from "../composables/useStoryContext";

const route = useRoute();
const router = useRouter();
const loading = ref(true);
const blocked = ref("");

const tabs = [
  { to: "adventure", label: "adventure" },
  { to: "world", label: "world" },
  { to: "party", label: "party" },
  { to: "journal", label: "journal" },
  { to: "diary", label: "diary" },
  { to: "relations", label: "relations" },
  { to: "eras", label: "eras" },
];

async function enter(id: string): Promise<void> {
  loading.value = true;
  blocked.value = "";
  try {
    await enterStory(id);
  } catch (error) {
    if (error instanceof ApiError && error.code === "PLAYER_UNBOUND") {
      blocked.value = "This player story has no bound character yet. Pick one in Stories.";
    } else {
      fail("story unavailable", error);
    }
    await router.replace("/stories");
  } finally {
    loading.value = false;
  }
}

watch(
  () => route.params.storyId,
  (next) => {
    if (typeof next === "string" && next !== currentStory.binding?.storyId) {
      void enter(next);
    }
  },
);

onUnmounted(() => {
  void leaveStory();
});

void enter(route.params.storyId as string);
</script>
<template>
  <div class="shell">
    <header class="topbar">
      <RouterLink to="/stories" class="brand back" title="Back to Stories">Stories</RouterLink>
      <span class="story-name">{{ currentStory.binding?.title ?? "" }}</span>
      <nav aria-label="Story">
        <RouterLink
          v-for="t in tabs"
          :key="t.to"
          :to="`/stories/${route.params.storyId}/${t.to}`"
        >{{ t.label }}</RouterLink>
      </nav>
      <span class="clock">{{ clock }}</span>
      <span class="conn" :data-state="connection">{{ connection }}</span>
    </header>
    <p class="notice" v-if="blocked">{{ blocked }}</p>
    <p class="notice" v-if="worldStatus !== 'active'">This story has ended. It stays inspectable; advance is disabled.</p>
    <p class="notice" v-if="notice">{{ notice }}</p>
    <RouterView v-if="!loading && !blocked" />
  </div>
</template>
