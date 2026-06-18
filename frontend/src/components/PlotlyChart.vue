<script setup lang="ts">
import { nextTick, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import Plotly from 'plotly.js-dist-min'

const props = defineProps<{
  plotlyJsonStr: string
}>()

const chartRef = ref<HTMLElement | null>(null)
let resizeObserver: ResizeObserver | null = null

const resizeChart = () => {
  if (!chartRef.value) return
  Plotly.Plots.resize(chartRef.value)
}

const renderChart = async () => {
  if (!chartRef.value || !props.plotlyJsonStr) return
  await nextTick()
  try {
    const dataAndLayout = JSON.parse(props.plotlyJsonStr)
    const data = dataAndLayout.data || []
    const rawLayout = dataAndLayout.layout || {}
    const { height: _height, width: _width, ...fluidLayout } = rawLayout
    const layout = {
      ...fluidLayout,
      autosize: true,
    }
    const config = { responsive: true, displayModeBar: false }
    await Plotly.react(chartRef.value, data, layout, config)
    requestAnimationFrame(resizeChart)
  } catch (err) {
    console.error('Failed to parse or render Plotly chart:', err)
  }
}

onMounted(() => {
  renderChart()
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => requestAnimationFrame(resizeChart))
    resizeObserver.observe(chartRef.value)
  }
})

watch(() => props.plotlyJsonStr, () => {
  renderChart()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  if (chartRef.value) {
    Plotly.purge(chartRef.value)
  }
})
</script>

<template>
  <div ref="chartRef" class="plotly-container"></div>
</template>
