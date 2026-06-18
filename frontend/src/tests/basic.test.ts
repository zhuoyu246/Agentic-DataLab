import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'

describe('Pinia Store Setup', () => {
  it('creates pinia instance', () => {
    const pinia = createPinia()
    expect(pinia).toBeDefined()
  })
})

describe('Basic Vue Component Test', () => {
  it('mounts a simple component', () => {
    const wrapper = mount({
      template: '<div>Hello Test</div>'
    })
    expect(wrapper.text()).toBe('Hello Test')
  })
})
