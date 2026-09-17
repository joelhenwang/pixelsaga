<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { portraitFor } from "./portrait";

const props = withDefaults(
  defineProps<{ assetId: string; name: string; size?: number }>(),
  { size: 44 },
);

const src = ref<string>("");

async function load(): Promise<void> {
  src.value = await portraitFor(props.assetId, props.name);
}

onMounted(() => {
  void load();
});
watch(() => [props.assetId, props.name], () => {
  void load();
});
</script>

<template>
  <img class="portrait" :src="src" :alt="`${props.name} portrait`" :width="props.size" :height="props.size" />
</template>
