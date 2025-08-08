<!-- src/components/LineChart.vue -->
<template>
  <!-- <div class="chart-container">
      <v-sheet class="pa-4 text-center">
        <v-progress-circular
          indeterminate
          color="primary"
        ></v-progress-circular>
        <div class="text-caption mt-2">Chart Loading...</div>
      </v-sheet>
    </div> -->
  

</template>

<script setup>
const axisName = [
  { name: 'X', color: 'red' },
  { name: 'Y', color: 'green' },
  { name: 'Z', color: 'blue' }

]

const sparklineData = [10, 15, 8, 12, 20, 25, 18];
</script>

<style scoped>
.sparkline {
  border: 1px solid #000;
  border-radius: 2px;
  padding: 4px;
  margin-bottom: 5px;
}
</style>