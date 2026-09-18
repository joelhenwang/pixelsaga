import { createRouter, createWebHistory } from "vue-router";
import ApplicationLayout from "./layouts/ApplicationLayout.vue";
import StoryLayout from "./layouts/StoryLayout.vue";
import CompatView from "./views/CompatView.vue";
import DiaryView from "./views/DiaryView.vue";
import GenerationsView from "./views/GenerationsView.vue";
import HelpView from "./views/HelpView.vue";
import HomeView from "./views/HomeView.vue";
import LibraryView from "./views/LibraryView.vue";
import NewStoryView from "./views/NewStoryView.vue";
import MapView from "./views/MapView.vue";
import OpsView from "./views/OpsView.vue";
import PartyView from "./views/PartyView.vue";
import PlayView from "./views/PlayView.vue";
import ProfileView from "./views/ProfileView.vue";
import RelationsView from "./views/RelationsView.vue";
import SceneView from "./views/SceneView.vue";
import SettingsView from "./views/SettingsView.vue";
import StoriesView from "./views/StoriesView.vue";
import TimelineView from "./views/TimelineView.vue";

const UUID_RE =
  "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      component: ApplicationLayout,
      children: [
        { path: "", name: "home", component: HomeView },
        { path: "stories", name: "stories", component: StoriesView },
        { path: "new-story", name: "new-story", component: NewStoryView },
        { path: "library", name: "library", component: LibraryView },
        { path: "library/:category", redirect: (to) => `/library?category=${to.params.category}` },
        { path: "settings", name: "settings", component: SettingsView },
        { path: "settings/:section", redirect: (to) => `/settings?section=${to.params.section}` },
        { path: "profile", name: "profile", component: ProfileView },
        { path: "help", name: "help", component: HelpView },
      ],
    },
    {
      path: `/stories/:storyId(${UUID_RE})`,
      component: StoryLayout,
      children: [
        { path: "play", name: "play", component: PlayView },
        { path: "adventure", name: "adventure", component: SceneView },
        { path: "world", name: "story-world", component: MapView },
        { path: "party", name: "story-party", component: PartyView },
        { path: "journal", name: "journal", component: TimelineView },
        { path: "diary", name: "diary", component: DiaryView },
        { path: "relations", name: "relations", component: RelationsView },
        { path: "eras", name: "eras", component: GenerationsView },
        { path: "operations", name: "operations", component: OpsView },
      ],
    },
    // Legacy gameplay bookmarks resolve through an explicit story.
    { path: "/scene", component: CompatView },
    { path: "/adventure", component: CompatView },
    { path: "/party", component: CompatView },
    { path: "/timeline", component: CompatView },
    { path: "/map", component: CompatView },
    { path: "/world", component: CompatView },
    { path: "/diary", component: CompatView },
    { path: "/relations", component: CompatView },
    { path: "/generations", component: CompatView },
    { path: "/operations", component: CompatView },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});
