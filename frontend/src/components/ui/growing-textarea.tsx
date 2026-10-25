import { useLayoutEffect, useRef, type TextareaHTMLAttributes } from 'react'

/** Expand prose fields with their content; keep scrolling in the document pane. */
export function GrowingTextarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const resize = () => { el.style.height = 'auto'; el.style.height = `${el.scrollHeight + 2}px` }
    resize()
    const observer = new ResizeObserver(() => {
      if (el.clientWidth !== width) { width = el.clientWidth; resize() }
    })
    let width = el.clientWidth
    observer.observe(el)
    return () => observer.disconnect()
  }, [props.value])
  return <textarea {...props} ref={ref} className={`growing-textarea ${props.className || ''}`} />
}
