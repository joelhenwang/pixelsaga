<!-- Settings (A07): provider, model, image, gameplay, storage,
  accessibility, advanced sections. Every control reaches a real
  consumer or is disabled with a reason; no success without a check. -->
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import type {
  CacheScopeView,
  PreferencesView,
  ProviderCapabilitiesView,
  ProviderConnectionView,
  ProviderProfileView,
  ProviderTestView,
} from "@gen";
import { api } from "../api";
import { fail, headers } from "../store";

const route = useRoute();
const section = ref("providers");
const prefs = ref<PreferencesView | null>(null);
const providers = ref<ProviderConnectionView[]>([]);
const profiles = ref<Record<string, ProviderProfileView[]>>({});
const capabilities = ref<Record<string, ProviderCapabilitiesView>>({});
const probes = ref<Record<string, ProviderTestView>>({});
const caches = ref<CacheScopeView[]>([]);
const savedNote = ref("");

// Provider form
const adapter = ref("fake");
const providerName = ref("");
const endpoint = ref("");
const credentialEnv = ref("");

// Profile form
const profileConnection = ref("");
const modelId = ref("");
const temperature = ref("");

async function load(): Promise<void> {
  try {
    prefs.value = await api.readPreferences(headers.value);
    providers.value = await api.listProviders(headers.value);
    caches.value = await api.listCaches(headers.value);
  } catch (error) {
    fail("settings unavailable", error);
  }
}

async function savePrefs(): Promise<void> {
  if (!prefs.value) return;
  try {
    prefs.value = await api.savePreferences(
      {
        gameplay: prefs.value.gameplay,
        accessibility: prefs.value.accessibility,
        profile: prefs.value.profile,
        expected_version: prefs.value.version,
      },
      headers.value,
    );
    savedNote.value = "Saved.";
  } catch (error) {
    fail("save failed", error);
  }
}

async function createProvider(): Promise<void> {
  try {
    const created = await api.createProvider(
      {
        adapter: adapter.value,
        name: providerName.value,
        endpoint: endpoint.value,
        credential_env: credentialEnv.value || null,
      },
      headers.value,
    );
    providers.value = await api.listProviders(headers.value);
    providerName.value = "";
    endpoint.value = "";
    credentialEnv.value = "";
    profileConnection.value = created.id;
  } catch (error) {
    fail("provider save failed", error);
  }
}

async function loadProfiles(connectionId: string): Promise<void> {
  try {
    profiles.value[connectionId] = await api.listProfiles(connectionId, headers.value);
    capabilities.value[connectionId] = await api.readCapabilities(connectionId, headers.value);
  } catch (error) {
    fail("profiles unavailable", error);
  }
}

async function addProfile(): Promise<void> {
  if (!profileConnection.value || !modelId.value) return;
  try {
    await api.addProfile(
      profileConnection.value,
      {
        model_id: modelId.value,
        temperature: temperature.value ? Number(temperature.value) : null,
      },
      headers.value,
    );
    profiles.value[profileConnection.value] = await api.listProfiles(
      profileConnection.value, headers.value,
    );
    modelId.value = "";
    temperature.value = "";
  } catch (error) {
    fail("profile save failed", error);
  }
}

async function testProvider(connectionId: string): Promise<void> {
  try {
    probes.value[connectionId] = await api.testProvider(connectionId, false, headers.value);
  } catch (error) {
    fail("probe failed", error);
  }
}

async function clearCache(scope: string): Promise<void> {
  try {
    await api.clearCache(scope, headers.value);
    caches.value = await api.listCaches(headers.value);
  } catch (error) {
    fail("cache clear failed", error);
  }
}

onMounted(() => {
  const direct = route.query.section;
  if (typeof direct === "string" && direct) section.value = direct;
  void load();
});
</script>
<template>
  <main class="page settings-page">
    <h1>Settings</h1>
    <div class="layout">
      <nav class="rail" aria-label="Settings sections">
        <button
          v-for="s in ['providers', 'model', 'images', 'gameplay', 'storage', 'access', 'advanced']"
          :key="s" type="button" :aria-pressed="section === s" @click="section = s"
        >{{ s }}</button>
      </nav>
      <div>
        <section v-if="section === 'providers'" class="panel">
          <h2>AI Providers</h2>
          <div v-for="p in providers" :key="p.id" class="group">
            <h3>{{ p.name }} &middot; {{ p.adapter }}</h3>
            <p>Credential: {{ p.has_credential ? "set" : "not set" }}. Key state only, never the secret.</p>
            <button type="button" @click="loadProfiles(p.id)">Show profiles</button>
            <button type="button" @click="testProvider(p.id)">Test connection</button>
            <p v-if="probes[p.id]">Probe: {{ probes[p.id].state }} &middot; {{ probes[p.id].text_ready }}</p>
            <ul v-if="profiles[p.id]">
              <li v-for="r in profiles[p.id]" :key="r.revision">
                rev {{ r.revision }} &middot; {{ r.model_id }}
                <span v-if="r.temperature !== null && r.temperature !== undefined">&middot; temp {{ r.temperature }}</span>
              </li>
            </ul>
          </div>
          <div class="group">
            <h3>New connection</h3>
            <label>Adapter
              <select v-model="adapter"><option value="fake">fake</option><option value="openrouter">openrouter</option></select>
            </label>
            <label>Name <input type="text" v-model="providerName" /></label>
            <label>Endpoint <input type="text" v-model="endpoint" placeholder="https://…" autocomplete="off" /></label>
            <label>Credential env var <input type="text" v-model="credentialEnv" placeholder="EMPTY means unchanged" autocomplete="off" /></label>
            <button type="button" @click="createProvider">Save connection</button>
          </div>
        </section>
        <section v-if="section === 'model'" class="panel">
          <h2>Language Model</h2>
          <label>Connection
            <select v-model="profileConnection" @change="profileConnection && loadProfiles(profileConnection)">
              <option value="">Choose…</option>
              <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </label>
          <label>Model ID <input type="text" v-model="modelId" /></label>
          <label>Temperature <input type="text" v-model="temperature" placeholder="0.0–2.0" /></label>
          <button type="button" @click="addProfile">Save profile revision</button>
          <p class="sub">Only parameters the adapter supports. Unsupported values are rejected, never ignored.</p>
        </section>
        <section v-if="section === 'images'" class="panel">
          <h2>Image Generation</h2>
          <p><b>Unavailable:</b> no live image adapter is configured. Curated starter art ships with Ember Vale.</p>
        </section>
        <section v-if="section === 'gameplay'" class="panel">
          <h2>Gameplay Defaults</h2>
          <div v-if="prefs">
            <label>Pacing
              <select v-model="(prefs.gameplay as Record<string, string>).pacing">
                <option value="measured">Measured</option>
                <option value="brisk">Brisk</option>
                <option value="slow burn">Slow burn</option>
              </select>
            </label>
            <button type="button" @click="savePrefs">Save changes</button>
            <p class="sub" v-if="savedNote">{{ savedNote }}</p>
          </div>
        </section>
        <section v-if="section === 'storage'" class="panel">
          <h2>Storage &amp; Data</h2>
          <div v-for="c in caches" :key="c.scope" class="group">
            <h3>{{ c.scope }} ({{ c.files }} files)</h3>
            <p>{{ c.description }}</p>
            <button type="button" @click="clearCache(c.scope)">Clear</button>
          </div>
        </section>
        <section v-if="section === 'access'" class="panel">
          <h2>Accessibility</h2>
          <div v-if="prefs">
            <label>Font scale
              <select v-model.number="(prefs.accessibility as Record<string, number>).font_scale">
                <option :value="100">100%</option>
                <option :value="112">112%</option>
                <option :value="125">125%</option>
              </select>
            </label>
            <button type="button" @click="savePrefs">Save changes</button>
          </div>
        </section>
        <section v-if="section === 'advanced'" class="panel">
          <h2>Advanced</h2>
          <p>Configuration source: environment plus operator profile revisions.</p>
          <RouterLink to="/stories">Open a story</RouterLink> to reach operations contextually.
        </section>
      </div>
    </div>
  </main>
</template>
