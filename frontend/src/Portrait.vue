<script setup lang="ts">
import { computed } from "vue";
import { portraitFor } from "./portrait";

const props = withDefaults(
  defineProps<{ assetId: string; name: string; size?: number }>(),
  { size: 44 },
);

const src = computed<string>(() => portraitFor(props.assetId));
</script>

<template>
  <img class="portrait" :src="src" :alt="`${props.name} portrait`" :width="props.size" :height="props.size" />
</template>
