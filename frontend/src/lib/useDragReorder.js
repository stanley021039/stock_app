import { useState } from 'react'

// Drag-to-reorder for table rows via a grip handle (HTML5 drag and drop).
// Shared by the 報價追蹤 tab and the PiP mini window -- both render rows
// through React, so this works the same inside the PiP document too.
//
// The DOM isn't reordered while dragging (moving the drag source node can
// cancel the drag in Chrome); instead the hovered row shows an insertion
// line, and the new order is committed once on drop.
export function useDragReorder(items, keyOf, onCommit) {
  const [dragKey, setDragKey] = useState(null)
  const [overKey, setOverKey] = useState(null)

  const indexOf = (k) => items.findIndex((x) => keyOf(x) === k)

  function clear() {
    setDragKey(null)
    setOverKey(null)
  }

  return {
    handleProps: (item) => ({
      draggable: true,
      title: '拖曳調整順序',
      onDragStart: (e) => {
        e.dataTransfer.effectAllowed = 'move'
        e.dataTransfer.setData('text/plain', keyOf(item))
        const row = e.currentTarget.closest('tr')
        if (row) e.dataTransfer.setDragImage(row, 12, 12)
        setDragKey(keyOf(item))
      },
      onDragEnd: clear,
      style: { cursor: 'grab', userSelect: 'none', color: 'var(--muted)', width: 18, textAlign: 'center' },
    }),

    rowProps: (item) => {
      const k = keyOf(item)
      let style
      if (dragKey != null && k === dragKey) {
        style = { opacity: 0.4 }
      } else if (dragKey != null && k === overKey) {
        // Line shows where the row will land: below the target when moving
        // down the list, above it when moving up.
        const below = indexOf(dragKey) < indexOf(k)
        style = { boxShadow: `inset 0 ${below ? -2 : 2}px 0 var(--accent)` }
      }
      return {
        style,
        onDragOver: (e) => {
          if (dragKey == null) return
          e.preventDefault()
          e.dataTransfer.dropEffect = 'move'
          if (overKey !== k) setOverKey(k)
        },
        onDrop: (e) => {
          e.preventDefault()
          const from = indexOf(dragKey)
          const to = indexOf(k)
          clear()
          if (from < 0 || to < 0 || from === to) return
          const next = [...items]
          const [moved] = next.splice(from, 1)
          next.splice(to, 0, moved)
          onCommit(next)
        },
      }
    },
  }
}
