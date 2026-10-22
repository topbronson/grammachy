// Loaded twice: by the QML overlay through `import "screens.js" as Screens`,
// and by `screens.test.js` under node. Nothing here may touch a QML or a node
// API, because each side only has one of them.
//
// The Settings picker draws every monitor as a rectangle in a miniature of
// the global layout, so the arithmetic lives here where a node test can read
// it, and the view only paints what these functions return.

function isFiniteNumber(value) {
  return typeof value === "number" && isFinite(value)
}

// The rows to draw: one { name, x, y, width, height } per usable screen,
// scaled into `box` from the global layout. Outputs sit at global positions
// that may be negative, so the whole layout is shifted to start at 0,0 and
// then fitted into the box with both axes kept inside it. A screen with no
// name or no size is dropped rather than drawn wrong, so an output unplugged
// between summons simply leaves the list.
function layoutOf(screens, box) {
  if (!Array.isArray(screens)) return []

  var usable = []
  for (var i = 0; i < screens.length; i++) {
    var screen = screens[i]
    if (!screen) continue
    if (typeof screen.name !== "string" || screen.name === "") continue
    if (!isFiniteNumber(screen.x) || !isFiniteNumber(screen.y)) continue
    if (!isFiniteNumber(screen.width) || !isFiniteNumber(screen.height)) continue
    if (screen.width <= 0 || screen.height <= 0) continue
    usable.push(screen)
  }
  if (usable.length === 0) return []

  var boxWidth = Math.max(1, Number(box && box.width) || 1)
  var boxHeight = Math.max(1, Number(box && box.height) || 1)

  var left = usable[0].x
  var top = usable[0].y
  var right = usable[0].x + usable[0].width
  var bottom = usable[0].y + usable[0].height
  for (var j = 1; j < usable.length; j++) {
    var row = usable[j]
    left = Math.min(left, row.x)
    top = Math.min(top, row.y)
    right = Math.max(right, row.x + row.width)
    bottom = Math.max(bottom, row.y + row.height)
  }

  var scale = Math.min(boxWidth / (right - left), boxHeight / (bottom - top))
  var out = []
  for (var k = 0; k < usable.length; k++) {
    var row = usable[k]
    out.push({
      name: row.name,
      x: (row.x - left) * scale,
      y: (row.y - top) * scale,
      width: row.width * scale,
      height: row.height * scale
    })
  }
  return out
}

// The live screen the popup is pinned to, or null when the stored name
// matches no live output — an unplugged monitor, or the unset `auto` setting.
// The membership check is what stops a stale name from being handed to
// `PanelWindow.screen` after the monitor it named has gone.
function screenNamed(screens, name) {
  if (!Array.isArray(screens)) return null
  if (typeof name !== "string" || name === "") return null
  for (var i = 0; i < screens.length; i++) {
    var screen = screens[i]
    if (screen && typeof screen.name === "string" && screen.name === name) return screen
  }
  return null
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    layoutOf: layoutOf,
    screenNamed: screenNamed
  }
}
