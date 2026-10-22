const test = require("node:test")
const assert = require("node:assert/strict")

const { layoutOf, screenNamed } = require("./screens.js")

const WIDE = { name: "DP-6", x: 1920, y: 0, width: 2560, height: 1440 }
const LEFT = { name: "DP-4", x: 0, y: 360, width: 1920, height: 1080 }
const ABOVE = { name: "HDMI-A-5", x: 2560, y: -720, width: 1920, height: 1080 }

test("nothing usable draws nothing", () => {
  assert.deepEqual(layoutOf(undefined, { width: 300, height: 120 }), [])
  assert.deepEqual(layoutOf([], { width: 300, height: 120 }), [])
  assert.deepEqual(layoutOf([null, {}, { name: "X", x: 0, y: 0 }], { width: 300, height: 120 }), [])
})

test("one screen fills the box it is fitted into", () => {
  const rows = layoutOf([LEFT], { width: 240, height: 135 })
  assert.equal(rows.length, 1)
  assert.deepEqual(rows[0], { name: "DP-4", x: 0, y: 0, width: 240, height: 135 })
})

test("the layout keeps both axes and starts at the box origin", () => {
  const box = { width: 300, height: 120 }
  const rows = layoutOf([LEFT, WIDE, ABOVE], box)
  assert.equal(rows.length, 3)

  assert.equal(rows[2].x, (2560 - 0) * (box.height / (1440 + 720)))
  assert.equal(rows[2].y, 0, "the screen above the others lands on the top edge")
  assert.equal(rows[0].y, (360 - -720) * (box.height / (1440 + 720)))

  for (const row of rows) {
    assert.ok(row.x >= 0 && row.y >= 0, row.name + " starts inside the box")
    assert.ok(row.x + row.width <= box.width + 0.0001, row.name + " ends inside the box")
    assert.ok(row.y + row.height <= box.height + 0.0001, row.name + " ends inside the box")
  }
})

test("a screen without a name or a size leaves the list", () => {
  const rows = layoutOf([LEFT, { x: 0, y: 0, width: 10, height: 10 }, { name: "gone", x: 0, y: 0, width: 0, height: 10 }],
    { width: 300, height: 120 })
  assert.deepEqual(rows.map(row => row.name), ["DP-4"])
})

test("the pin reads back only a live screen", () => {
  const screens = [LEFT, WIDE]
  assert.equal(screenNamed(screens, "DP-6"), WIDE)
  assert.equal(screenNamed(screens, "DP-9"), null, "a name no output answers to")
  assert.equal(screenNamed(screens, ""), null, "the auto setting names no screen")
  assert.equal(screenNamed(screens, undefined), null)
  assert.equal(screenNamed(undefined, "DP-6"), null)
})
