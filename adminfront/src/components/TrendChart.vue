<template>
  <div ref="chartRef" class="chart-surface"></div>
</template>

<script setup>
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  series: { type: Array, default: () => [] },
  categories: { type: Array, default: () => [] },
  title: { type: String, default: '' },
})

const chartRef = ref(null)
let chart = null

function render() {
  if (!chartRef.value) {
    return
  }
  if (!chart) {
    chart = echarts.init(chartRef.value)
  }
  chart.setOption({
    backgroundColor: 'transparent',
    title: { text: props.title, left: 12, top: 12, textStyle: { color: '#e7dfd0', fontSize: 14, fontWeight: 600 } },
    tooltip: { trigger: 'axis' },
    legend: { top: 12, right: 16, textStyle: { color: '#c9c0b1' } },
    grid: { left: 48, right: 24, top: 56, bottom: 36 },
    xAxis: {
      type: 'category',
      data: props.categories,
      axisLine: { lineStyle: { color: 'rgba(231,223,208,0.2)' } },
      axisLabel: { color: '#a89d8d' },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: 'rgba(231,223,208,0.08)' } },
      axisLabel: { color: '#a89d8d' },
    },
    series: props.series,
  })
}

onMounted(() => {
  render()
  window.addEventListener('resize', render)
})

watch(() => [props.series, props.categories], render, { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('resize', render)
  if (chart) {
    chart.dispose()
  }
})
</script>
