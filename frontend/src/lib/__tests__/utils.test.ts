import { describe, it, expect } from 'vitest'
import { cn, extractApiError } from '../utils'

describe('cn', () => {
  it('合并多个类名', () => {
    expect(cn('foo', 'bar')).toBe('foo bar')
  })

  it('处理条件类名(过滤 falsy 值)', () => {
    expect(cn('foo', false && 'bar', undefined, null, 0, 'baz')).toBe('foo baz')
  })

  it('tailwind 冲突类去重(后者优先)', () => {
    expect(cn('px-2 py-1', 'px-4')).toBe('py-1 px-4')
  })

  it('空输入返回空字符串', () => {
    expect(cn()).toBe('')
  })
})

describe('extractApiError', () => {
  it('从 axios 错误中提取 detail', () => {
    const err = { response: { data: { detail: '参数错误' } } }
    expect(extractApiError(err)).toBe('参数错误')
  })

  it('无 detail 时回退到 Error.message', () => {
    expect(extractApiError(new Error('网络超时'))).toBe('网络超时')
  })

  it('其他类型回退到 String()', () => {
    expect(extractApiError('字符串错误')).toBe('字符串错误')
  })
})
