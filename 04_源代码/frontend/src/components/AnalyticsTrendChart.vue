<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { init, use, type ECharts } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import type { PolicyInsights } from '../types/api'

use([LineChart, GridComponent, LegendComponent, TooltipComponent, SVGRenderer])

const props = defineProps<{ data: PolicyInsights['daily_trend'] }>()
const chartRoot = ref<HTMLElement | null>(null)
let chart: ECharts | null = null
let resizeObserver: ResizeObserver | null = null

function render(): void {
  if (!chartRoot.value || import.meta.env.MODE === 'test') return
  chart ??= init(chartRoot.value, undefined, { renderer: 'svg' })
  chart.setOption({
    animationDuration: 420,
    color: ['#176b55', '#c96d3b'],
    tooltip: {
      trigger: 'axis',
      formatter: (params: Array<{ dataIndex: number; marker: string; seriesName: string; value: number }>) => {
        const row = props.data[params[0]?.dataIndex ?? 0]
        const values = params.map((item) => `${item.marker}${item.seriesName}：${item.value}`).join('<br/>')
        return `${row?.date || ''}<br/>${values}${row?.leading_category ? `<br/>主要类别：${row.leading_category}` : ''}`
      },
    },
    legend: { top: 0, textStyle: { color: '#667a73' } },
    grid: { left: 42, right: 24, top: 44, bottom: 28 },
    xAxis: { type: 'category', data: props.data.map((item) => item.date.slice(5)), boundaryGap: false },
    yAxis: { type: 'value', name: '次数', min: 0, minInterval: 1 },
    series: [
      { name: '员工咨询量', type: 'line', smooth: true, data: props.data.map((item) => item.consultations), areaStyle: { opacity: 0.08 } },
      { name: '新增制度问题', type: 'line', smooth: true, data: props.data.map((item) => item.new_issues) },
    ],
  }, true)
}

watch(() => props.data, () => nextTick(render), { deep: true })
onMounted(async () => {
  await nextTick()
  render()
  if (typeof ResizeObserver !== 'undefined' && chartRoot.value) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartRoot.value)
  }
})
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
})
</script>

<template><div ref="chartRoot" class="analytics-trend-chart" role="img" aria-label="员工咨询与制度问题趋势图"></div></template>
