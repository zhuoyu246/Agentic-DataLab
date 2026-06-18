<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { BarChart3, ChevronDown, Database, FileCode, TableProperties } from 'lucide-vue-next'
import { api, type ArtifactEnvelope, type DatasetPreview } from '../api/client'
import { useWorkspace } from '../stores/useWorkspace'
import PlotlyChart from './PlotlyChart.vue'

const workspace = useWorkspace()
const activeKind = ref('all')
const selectedArtifactId = ref<string | null>(null)
const lastArtifactCount = ref(0)
const preview = ref<DatasetPreview | null>(null)
const previewOpen = ref(false)
const previewLoading = ref(false)
const previewError = ref<string | null>(null)

const kinds = computed(() => {
  const values = new Set(workspace.artifacts.map((a) => a.kind))
  return ['all', ...Array.from(values)]
})

const filteredArtifacts = computed(() =>
  activeKind.value === 'all'
    ? workspace.artifacts
    : workspace.artifacts.filter((artifact) => artifact.kind === activeKind.value),
)

const selectedDataset = computed(() => workspace.selectedDataset)

const selectedArtifact = computed<ArtifactEnvelope | null>(() => {
  if (!filteredArtifacts.value.length) return null
  return (
    filteredArtifacts.value.find((artifact) => artifact.id === selectedArtifactId.value)
    ?? filteredArtifacts.value[0]
  )
})

const metricEntries = (payload: Record<string, unknown>) => {
  const metrics = payload.metrics
  if (!metrics || typeof metrics !== 'object') return []
  return Object.entries(metrics as Record<string, unknown>)
}

const listPayload = (payload: Record<string, unknown>, key: string) => {
  const value = payload[key]
  return Array.isArray(value) ? value.map((item) => String(item)) : []
}

const preprocessingLists = (payload: Record<string, unknown>) => {
  const preprocessing = payload.preprocessing
  if (!preprocessing || typeof preprocessing !== 'object') return []
  return Object.entries(preprocessing as Record<string, unknown>)
    .filter(([, value]) => Array.isArray(value))
    .map(([key, value]) => ({ key, values: (value as unknown[]).map((item) => String(item)) }))
    .filter((item) => item.values.length)
}

const artifactIcon = (artifact: ArtifactEnvelope) => {
  if (artifact.kind.includes('chart')) return BarChart3
  if (artifact.kind.includes('dataset') || artifact.kind.includes('feature')) return TableProperties
  return FileCode
}

const preferredArtifact = (items: ArtifactEnvelope[]) =>
  [...items].reverse().find((artifact) => artifact.kind === 'plotly_chart') ?? items[items.length - 1]

function selectKind(kind: string) {
  activeKind.value = kind
  selectedArtifactId.value = null
}

async function loadPreview() {
  preview.value = null
  previewError.value = null
  if (!workspace.session || !workspace.selectedDatasetId) return
  previewLoading.value = true
  try {
    preview.value = await api.previewDataset(workspace.session.id, workspace.selectedDatasetId, 8)
  } catch (error) {
    previewError.value = error instanceof Error ? error.message : String(error)
  } finally {
    previewLoading.value = false
  }
}

watch(
  () => [workspace.session?.id, workspace.selectedDatasetId, workspace.session?.updated_at],
  () => {
    previewOpen.value = false
    loadPreview()
  },
  { immediate: true },
)

watch(
  filteredArtifacts,
  (items) => {
    if (!items.length) {
      selectedArtifactId.value = null
      lastArtifactCount.value = 0
      return
    }
    const selectedStillExists = Boolean(
      selectedArtifactId.value && items.some((item) => item.id === selectedArtifactId.value),
    )
    const hasNewArtifacts = items.length > lastArtifactCount.value
    if (!selectedStillExists || hasNewArtifacts) {
      selectedArtifactId.value = preferredArtifact(items).id
    }
    lastArtifactCount.value = items.length
  },
  { immediate: true },
)
</script>

<template>
  <div class="artifact-layout">
    <section v-if="selectedDataset" class="dataset-strip" :data-open="previewOpen">
      <button type="button" class="dataset-strip-main" @click="previewOpen = !previewOpen">
        <Database :size="16" />
        <span>
          <strong>{{ selectedDataset.label }}</strong>
          <small>{{ selectedDataset.stage }} · {{ selectedDataset.shape[0] }} x {{ selectedDataset.shape[1] }}</small>
        </span>
        <ChevronDown :size="16" />
      </button>

      <div v-if="previewOpen" class="dataset-preview">
        <div v-if="previewError" class="preview-state">{{ previewError }}</div>
        <div v-else-if="previewLoading" class="preview-state">Loading preview...</div>
        <div v-else-if="preview" class="preview-table-wrap">
          <table>
            <thead>
              <tr>
                <th v-for="column in preview.columns.slice(0, 8)" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in preview.rows" :key="index">
                <td v-for="column in preview.columns.slice(0, 8)" :key="column">{{ String(row[column] ?? '') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <div class="tabs artifact-tabs">
      <button
        v-for="kind in kinds"
        :key="kind"
        :class="{ active: activeKind === kind }"
        @click="selectKind(kind)"
      >
        {{ kind }}
      </button>
    </div>

    <div class="artifact-workspace">
      <nav class="artifact-rail">
        <button
          v-for="artifact in filteredArtifacts"
          :key="artifact.id"
          type="button"
          :class="{ active: selectedArtifact?.id === artifact.id }"
          @click="selectedArtifactId = artifact.id"
        >
          <component :is="artifactIcon(artifact)" :size="16" />
          <span>
            <strong>{{ artifact.title }}</strong>
            <small>{{ artifact.kind }}</small>
          </span>
        </button>
      </nav>

      <section class="artifact-detail">
        <template v-if="selectedArtifact">
          <header class="artifact-detail-header">
            <div>
              <strong>{{ selectedArtifact.title }}</strong>
              <span>{{ selectedArtifact.kind }}</span>
            </div>
            <span v-if="selectedArtifact.degraded" class="degraded-pill">degraded</span>
          </header>

          <div
            class="artifact-detail-body"
            :class="{ 'chart-body': selectedArtifact.kind === 'plotly_chart' }"
          >
            <template v-if="selectedArtifact.kind === 'plotly_chart'">
              <PlotlyChart :plotlyJsonStr="String(selectedArtifact.payload.plotly_json)" />
              <div class="chart-meta">
                <span v-if="selectedArtifact.payload.rows_used">Rendered from {{ selectedArtifact.payload.rows_used }} / {{ selectedArtifact.payload.source_rows }} rows</span>
              </div>
            </template>

            <template v-else-if="selectedArtifact.kind === 'model_info'">
              <div class="model-summary">
                <div>
                  <span>task</span>
                  <strong>{{ selectedArtifact.payload.task || 'model' }}</strong>
                </div>
                <div>
                  <span>engine</span>
                  <strong>{{ selectedArtifact.payload.engine || 'unknown' }}</strong>
                </div>
                <div>
                  <span>best</span>
                  <strong>{{ selectedArtifact.payload.best_model || '-' }}</strong>
                </div>
                <div>
                  <span>run</span>
                  <strong>{{ selectedArtifact.payload.run_id || '-' }}</strong>
                </div>
              </div>
              <div class="metric-grid">
                <div v-for="[key, value] in metricEntries(selectedArtifact.payload)" :key="key">
                  <span>{{ key }}</span>
                  <strong>{{ typeof value === 'number' ? value.toFixed(4) : value }}</strong>
                </div>
              </div>
              <div v-if="preprocessingLists(selectedArtifact.payload).length" class="preprocess-list">
                <section v-for="item in preprocessingLists(selectedArtifact.payload)" :key="item.key">
                  <strong>{{ item.key }}</strong>
                  <span>{{ item.values.slice(0, 12).join(', ') }}{{ item.values.length > 12 ? '...' : '' }}</span>
                </section>
              </div>
            </template>

            <template v-else-if="selectedArtifact.kind === 'feature_report'">
              <div class="metric-grid">
                <div>
                  <span>target</span>
                  <strong>{{ selectedArtifact.payload.target_preserved || '-' }}</strong>
                </div>
                <div>
                  <span>shape</span>
                  <strong>{{ Array.isArray(selectedArtifact.payload.shape) ? selectedArtifact.payload.shape.join(' x ') : '-' }}</strong>
                </div>
                <div>
                  <span>added</span>
                  <strong>{{ listPayload(selectedArtifact.payload, 'added_columns').length }}</strong>
                </div>
                <div>
                  <span>frequency</span>
                  <strong>{{ listPayload(selectedArtifact.payload, 'frequency_encoded').length }}</strong>
                </div>
              </div>
              <pre>{{ JSON.stringify(selectedArtifact.payload.model_time_encoding, null, 2) }}</pre>
            </template>

            <template v-else-if="selectedArtifact.kind === 'eda_report'">
              <div class="metric-grid">
                <div>
                  <span>rows</span>
                  <strong>{{ Array.isArray(selectedArtifact.payload.shape) ? selectedArtifact.payload.shape[0] : '-' }}</strong>
                </div>
                <div>
                  <span>columns</span>
                  <strong>{{ Array.isArray(selectedArtifact.payload.shape) ? selectedArtifact.payload.shape[1] : '-' }}</strong>
                </div>
                <div>
                  <span>profile</span>
                  <strong>{{ Object.keys(selectedArtifact.payload.cardinality || {}).length }}</strong>
                </div>
              </div>
              <pre>{{ JSON.stringify(selectedArtifact.payload.missing, null, 2) }}</pre>
            </template>

            <pre v-else>{{ JSON.stringify(selectedArtifact.payload, null, 2) }}</pre>
          </div>
        </template>

        <div v-else class="empty-artifacts">
          No artifacts yet.
        </div>
      </section>
    </div>
  </div>
</template>
