import { createRouter, createWebHistory } from "vue-router";
import DiaryView from "./views/DiaryView.vue";
import GenerationsView from "./views/GenerationsView.vue";
import MapView from "./views/MapView.vue";
import OpsView from "./views/OpsView.vue";
import PartyView from "./views/PartyView.vue";
import RelationsView from "./views/RelationsView.vue";
import SceneView from "./views/SceneView.vue";
import TimelineView from "./views/TimelineView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/scene" },
    { path: "/scene", component: SceneView },
    { path: "/adventure", redirect: "/scene" },
    { path: "/party", component: PartyView },
    { path: "/timeline", component: TimelineView },
    { path: "/map", component: MapView },
    { path: "/world", redirect: "/map" },
    { path: "/diary", component: DiaryView },
    { path: "/relations", component: RelationsView },
    { path: "/generations", component: GenerationsView },
    { path: "/operations", component: OpsView },
  ],
});
