<script setup lang="ts">
import { computed, ref } from 'vue'
import { FileCode, TableProperties, BarChart3 } from 'lucide-vue-next'
import { useWorkspace } from '../stores/useWorkspace'
import PlotlyChart from './PlotlyChart.vue'

const workspace = useWorkspace()
const activeKind = ref('all')

const kinds = computed(() => {
  const values = new Set(workspace.artifacts.map((a) => a.kind))
  return ['all', ...Array.from(values)]
})

const artifacts = computed(() =>
  activeKind.value === 'all'
    ? workspace.artifacts
    : workspace.artifacts.filter((artifact) => artifact.kind === activeKind.value),
)
</script>

<template>
  <div class="artifact-layout">
    <div class="tabs">
      <button
        v-for="kind in kinds"
        :key="kind"
        :class="{ active: activeKind === kind }"
        @click="activeKind = kind"
      >
        {{ kind }}
      </button>
    </div>

    <div class="artifact-list">
      <article v-for="artifact in artifacts" :key="artifact.id" class="artifact-card">
        <header>
          <BarChart3 v-if="artifact.kind.includes('chart')" :size="17" />
          <TableProperties v-else-if="artifact.kind.includes('dataset')" :size="17" />
          <FileCode v-else :size="17" />
          <strong>{{ artifact.title }}</strong>
          <span v-if="artifact.degraded">degraded</span>
        </header>

        <div class="artifact-content">
          <template v-if="artifact.kind === 'plotly_chart'">
            <PlotlyChart :plotlyJsonStr="String(artifact.payload.plotly_json)" />
            <div class="chart-meta" style="margin-top: 8px; font-size: 0.85em; color: #666;">
              <span v-if="artifact.payload.rows_used">Rendered from {{ artifact.payload.rows_used }} / {{ artifact.payload.source_rows }} rows</span>
            </div>
          </template>
          <pre v-else>{{ JSON.stringify(artifact.payload, null, 2) }}</pre>
        </div>
      </article>
    </div>
  </div>
</template>

