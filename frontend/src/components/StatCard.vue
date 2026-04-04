<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    label: string
    value: string
    helper: string
    tone?: 'amber' | 'teal' | 'coral' | 'slate'
  }>(),
  {
    tone: 'slate',
  },
)

const toneClass = computed(() => `tone-${props.tone}`)
</script>

<template>
  <article class="metric-card" :class="toneClass">
    <div class="metric-card__icon">
      <slot />
    </div>
    <div class="metric-card__body">
      <p class="metric-card__label">{{ label }}</p>
      <strong class="metric-card__value">{{ value }}</strong>
      <span class="metric-card__helper">{{ helper }}</span>
    </div>
  </article>
</template>

<style scoped>
.metric-card {
  display: flex;
  gap: 14px;
  padding: 18px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 22px;
  background: rgba(11, 17, 24, 0.72);
  box-shadow: 0 18px 48px rgba(3, 8, 15, 0.26);
  min-height: 118px;
}

.metric-card__icon {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: 16px;
  color: white;
  flex-shrink: 0;
}

.metric-card__body {
  display: grid;
  gap: 8px;
}

.metric-card__label {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.metric-card__value {
  font-size: 29px;
  line-height: 1;
}

.metric-card__helper {
  color: var(--muted);
  font-size: 13px;
}

.tone-amber .metric-card__icon {
  background: linear-gradient(135deg, rgba(255, 169, 77, 0.92), rgba(255, 118, 64, 0.88));
}

.tone-teal .metric-card__icon {
  background: linear-gradient(135deg, rgba(42, 182, 172, 0.92), rgba(43, 108, 176, 0.84));
}

.tone-coral .metric-card__icon {
  background: linear-gradient(135deg, rgba(245, 110, 122, 0.9), rgba(234, 136, 84, 0.86));
}

.tone-slate .metric-card__icon {
  background: linear-gradient(135deg, rgba(97, 114, 140, 0.88), rgba(62, 78, 104, 0.92));
}
</style>
