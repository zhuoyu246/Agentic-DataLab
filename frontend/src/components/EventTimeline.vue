<script setup lang="ts">
import { Activity } from 'lucide-vue-next'
import { useWorkspace } from '../stores/useWorkspace'

const workspace = useWorkspace()
</script>

<template>
  <div class="panel-title compact">
    <Activity :size="18" />
    <span>Run Timeline</span>
  </div>
  <div class="timeline">
    <article v-for="event in workspace.events" :key="event.id" :data-type="event.type">
      <strong>{{ event.agent_name || event.type }}</strong>
      <span>{{ event.message }}</span>
    </article>
  </div>
</template>

