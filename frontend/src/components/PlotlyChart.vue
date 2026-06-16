<script setup lang="ts">
import { nextTick, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import Plotly from 'plotly.js-dist-min'

const props = defineProps<{
  plotlyJsonStr: string
}>()

const chartRef = ref<HTMLElement | null>(null)

const renderChart = async () => {
  if (!chartRef.value || !props.plotlyJsonStr) return
  await nextTick()
  try {
    const dataAndLayout = JSON.parse(props.plotlyJsonStr)
    const data = dataAndLayout.data || []
    const layout = dataAndLayout.layout || {}
    const config = { responsive: true, displayModeBar: false }
    Plotly.react(chartRef.value, data, layout, config)
    requestAnimationFrame(() => {
      if (chartRef.value) Plotly.Plots.resize(chartRef.value)
    })
  } catch (err) {
    console.error('Failed to parse or render Plotly chart:', err)
  }
}

onMounted(() => {
  renderChart()
})

watch(() => props.plotlyJsonStr, () => {
  renderChart()
})

onBeforeUnmount(() => {
  if (chartRef.value) {
    Plotly.purge(chartRef.value)
  }
})
</script>

<template>
  <div ref="chartRef" class="plotly-container"></div>
</template>
