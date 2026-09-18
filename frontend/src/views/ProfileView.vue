<!-- Local operator profile (A07): display name and installation
  access state. Never a character portrait, never a cloud login. -->
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "../api";
import { fail, headers } from "../store";

const displayName = ref("Storyteller");
const version = ref(0);

async function load(): Promise<void> {
  try {
    const prefs = await api.readPreferences(headers.value);
    displayName.value = (prefs.profile as Record<string, string>).display_name ?? "Storyteller";
    version.value = prefs.version;
  } catch (error) {
    fail("profile unavailable", error);
  }
}

async function save(): Promise<void> {
  try {
    const saved = await api.savePreferences(
      { profile: { display_name: displayName.value }, expected_version: version.value },
      headers.value,
    );
    displayName.value = (saved.profile as Record<string, string>).display_name;
    version.value = saved.version;
  } catch (error) {
    fail("profile save failed", error);
  }
}

onMounted(() => {
  void load();
});
</script>
<template>
  <main class="page narrow">
    <h1>Local profile</h1>
    <p class="sub">This installation has one operator. No account, no sign-in.</p>
    <label>Display name <input type="text" v-model="displayName" /></label>
    <button type="button" @click="save">Save</button>
  </main>
</template>
