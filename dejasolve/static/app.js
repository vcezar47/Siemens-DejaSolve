const $ = (s) => document.querySelector(s);
//: `'` was missing from both the character class and the replacement map --
//: harmless while every attribute in this file is double-quoted, but that
//: made the helper correct by convention rather than by construction, one
//: single-quoted attribute away from being wrong.
const esc = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c],
  );
const fmt = (v) =>
  v === null || v === undefined
    ? ""
    : Math.abs(v) >= 1e-4 && Math.abs(v) < 1e6
      ? (+v.toPrecision(6)).toString()
      : v.toExponential(3);

let SAMPLES = [];

//: `prefers-reduced-motion` used to stop exactly four things: the wordmark's
//: moving gradient, the run button's gradient, the header's accent bar, and
//: the page's own drifting background bloom -- all decoration. It did not
//: reach the three things on this page that actually move: the spinning 3D
//: cloud and machine views, the shaft-speed marks rotating at their solved
//: rev/min, and the fluid particles travelling the pipes. A user who has
//: asked the OS for less motion got the static gradients and all of the
//: moving machinery. `GEO.spin` / `MACH.spin` read this at boot to start
//: still rather than spinning -- the Spin/Stop buttons remain, so nothing the
//: preference should not touch is lost, only the *default*. The
//: `matchMedia` listener keeps it current if the OS setting changes with the
//: page open.
const REDUCED_MOTION_QUERY = matchMedia(
  "(prefers-reduced-motion: reduce)",
);
let REDUCED_MOTION = REDUCED_MOTION_QUERY.matches;
REDUCED_MOTION_QUERY.addEventListener("change", (e) => {
  REDUCED_MOTION = e.matches;
});

//: label for each backend id. `auto` is always offered and always works —
//: it degrades to the parser rather than failing.
const BACKEND_LABEL = {
  hybrid: "hybrid (parser + local model)",
  rules: "rules only (instant)",
  ollama: "Ollama only (local)",
};

//: last health payload, so `explain()` can describe the current selection
//: without another round trip
let HEALTH = {};

function renderHealth(h) {
  HEALTH = h;
  const B = h.backends || {};
  const ready = Object.keys(B).filter((k) => B[k].available);

  // "cases" was true until the failed runs were kept as well. Both halves, and
  // the failed one is amber rather than red: a failed run is not an error, it is
  // the more expensive half of what the archive knows.
  const failed = h.archive_failed
    ? ` <span style="color:var(--warn)">&middot; <b>${h.archive_failed}</b> failed</span>`
    : "";
  //: each stat gets a category accent (--badge-accent) so archive / ingest /
  //: local read as three distinct facts at a glance, the way a dashboard's
  //: KPI row does, rather than as one run of small grey text.
  $("#badges").innerHTML =
    `<span class="badge" style="--badge-accent:var(--grad-1)">archive
 <b>${h.archive_size}</b> solved${failed}</span>` +
    `<span class="badge" style="--badge-accent:var(--grad-3)">ingest
 <b>${ready.join(" + ") || "none"}</b></span>` +
    (B.ollama && B.ollama.available
      ? `<span class="badge" style="--badge-accent:var(--ok);color:var(--ok)">local
     <b>on-prem</b></span>`
      : "");

  // Whatever /api/health offers is what the page offers — the list is not
  // written out here, so a backend can never exist on one side only.
  // Unavailable ones stay visible with the reason in the label; hiding them
  // is how a demo ends up with an unexplained missing feature.
  // `auto` is deliberately absent from this list, though it remains the default
  // for the CLI and `POST /api/analyse`. A dropdown entry whose meaning changes
  // with what happens to be running is the wrong thing to have on a stage: the
  // page's whole argument is that it shows which component did what, and an
  // option that silently resolves to hybrid or to rules hides exactly that.
  // Choosing the backend by name means the demo can never be asked "so which
  // one actually ran?" without the screen already answering.
  const sel = $("#backend");
  const keep = sel.value; // survive a refresh mid-demo
  const markup = Object.keys(B)
    .map(
      (k) =>
        `<option class="${B[k].available ? "on" : "off"}" value="${k}"` +
        `${B[k].available ? "" : ' data-off="1"'}>ingest: ${BACKEND_LABEL[k] || k}` +
        `${B[k].available ? "" : " - unavailable"}</option>`,
    )
    .join("");
  // Rebuilding on every poll would close an open dropdown under the user's
  // cursor, so only touch the DOM when the availability picture changed.
  if (sel.innerHTML !== markup) {
    sel.innerHTML = markup;
    // keep the operator's choice across a poll; otherwise open on the best
    // backend that is actually up, which is what `auto` used to decide silently
    sel.value = [...sel.options].some((x) => x.value === keep)
      ? keep
      : B.hybrid && B.hybrid.available
        ? "hybrid"
        : "rules";
  }
  explain();
}

function explain() {
  const sel = $("#backend");
  const B = HEALTH.backends || {};
  const o = sel.selectedOptions[0];
  const k = sel.value;
  $("#hint").textContent = B[k] ? B[k].detail : "";
  const off = !!(o && o.dataset.off);
  $("#hint").style.color = off ? "var(--refuse)" : "var(--ok)";
  sel.classList.toggle("off", off);
  sel.classList.toggle("on", !off);
}

//: Health is a live property, not a load-time fact: Ollama can come up or go
//: away while the page sits open. Re-read it rather than leaving the page
//: asserting something that stopped being true — a demo that says
//: "unavailable" about a backend you just fixed is the worst kind of wrong.
async function refreshHealth() {
  try {
    renderHealth(await (await fetch("/api/health")).json());
  } catch (e) {
    /* transient: keep showing the last known state */
  }
}

/* --- the geometry view --------------------------------------------------
//: Three beats on one viewport: where the archive's solved states sit, which
//: one was retrieved for a query, and what the solver then does from each
//: starting guess. Hand-drawn SVG for the same reason every other graphic here
//: is — one file, no CDN, and a conference room with no internet. (This used to
//: read "for the same reason as lineChart above"; `lineChart` left with the
//: Evidence panel and the comment kept pointing at it.)
//:
//: Everything drawn here comes from viz_results.json, which `benchmarks/viz.py` refuses
//: to write if its iteration counts disagree with results.json. The picture
//: cannot quote a number the benchmark does not.
*/
let VIZ = null;
/* --- the analysed case, placed in the same space -------------------------
//: Everything above draws what `benchmarks/viz.py` measured offline. This connects it to
//: what the operator just ran: the case they analysed is projected with the
//: *published transform* -- the same mu/sd/basis the archive was projected
//: with -- so a case the archive has never seen lands in the archive's own
//: coordinates rather than in a second, incomparable picture.
//:
//: No geometry is computed here that the pipeline did not already compute.
//: `POST /api/analyse` returns the solved state, the retrieved neighbour's
//: state and the three Newton paths; this only multiplies them by a matrix.
*/
let LIVE = null;

function projectState(sol) {
  const T = VIZ.projection.transform;
  const z = T.state_order.map(
    (k, i) => (sol[k] - T.mu[i]) / T.sd[i] - T.centre[i],
  );
  return T.basis.map((row) => row.reduce((a, w, i) => a + w * z[i], 0));
}

//: a live case is only placeable once it has actually been solved. A refusal --
//: incomplete card, foreign domain, blocked transfer -- has no solved state, and
//: inventing a position for it would be the one dishonesty this whole view is
//: built to avoid. Those return null and the views keep showing the fixture.
function liveFromTrace(t) {
  const sol = t && t.solve && t.solve.solution;
  const ret = t && t.retrieval;
  if (!sol || !ret || !ret.solution) return null;
  return {
    id: t.artifact || "your run",
    params: t.card.params,
    solution: sol,
    xyz: projectState(sol),
    relief_open: !!(t.solve.regime && t.solve.regime.relief_open),
    neighbour: {
      id: ret.case_id,
      params: ret.params,
      solution: ret.solution,
      xyz: projectState(ret.solution),
      relief_open: !!(ret.regime && ret.regime.relief_open),
    },
    distance: ret.distance,
    //: how retrieval picked this case, and which transfer order the solver then
    //: used. Both are carried because the panel below draws this case as "what
    //: retrieval chose" -- and if it was chosen over a nearer one, or started
    //: from with curvature rather than verbatim, a view that cannot say so is
    //: describing a simpler pipeline than the one that ran.
    ranking: ret.ranking || null,
    transfer: t.solve.transfer || null,
    paths: t.solve.paths || {},
    iterations: {
      cold: t.solve.cold_iterations,
      nominal: t.solve.nominal_iterations,
      warm: t.solve.warm_iterations,
    },
    //: which arms actually converged, carried alongside their counts. A count
    //: on its own cannot be read: the cold arm reports the iteration it stalled
    //: on exactly as it reports the iteration it finished on.
    converged: {
      cold: t.solve.cold_converged,
      nominal: t.solve.nominal_converged,
      warm: t.solve.warm_converged,
    },
    agreement: t.solve.agreement,
    agreementAgainst: t.solve.agreement_against,
    //: whether the archive was used at all. A warned transfer the engineer left
    //: standing still retrieves a neighbour and still reports it -- it just
    //: never starts from it -- so `neighbour` being present is not the same
    //: statement as "this run warm-started", and the panels below must not read
    //: it as one.
    usedArchive: t.solve.warm_iterations !== undefined,
    outcome: t.outcome,
  };
}

//: every panel in this section, re-rendered from whatever `LIVE` now is. One
//: function because they must never be refreshed in different combinations --
//: updating the view and the machine panel but not the contact sheet is exactly
//: how the sheet came to quote a different case from the banner above it.
function renderGeoAll() {
  GEO.bounds = geoBounds(); // the live paths may reach further out
  //: same reasoning -- a live case's own p1 can exceed the fixture's ceiling,
  //: and PSCALE drives the colour ramp in both the 3D machine view and the
  //: contact-sheet tiles, so it has to track whichever case is on screen the
  //: same way `GEO.bounds` already does.
  recomputePScale();
  renderControls();
  renderView();
  renderMachPanel();
  renderFailures();
  renderGeoNums();
  if (typeof updateStepperUI === "function") updateStepperUI();
}

//: back to the exemplar `benchmarks/viz.py` shipped, with an optional line saying why.
//: Used by the "Show the shipped example" button and by `adoptTrace` when a run
//: is refused -- both need the same teardown, and having only the button do it
//: is what left a refused run showing the previous case's geometry.
function showFixture(note) {
  LIVE = null;
  MACH.right = null;
  MACH.overrideState = null;
  MACH.overrideLabel = null;
  GEO.sel = null;
  document
    .querySelectorAll(".tile")
    .forEach((x) => x.classList.remove("on"));
  $("#liverow").innerHTML = note || "";
  renderGeoAll();
}

function adoptTrace(t) {
  const live = liveFromTrace(t);
  if (!live) {
    //: A refusal has no solved state, so there is nothing to place in a space
    //: built out of solved states, and inventing a position for it is the one
    //: dishonesty this view exists to avoid.
    //:
    //: But "nothing to place" was implemented as an early return, and `LIVE` was
    //: never cleared -- so the *previous* run stayed on screen underneath a
    //: banner reading "the artifact you just analysed". Analyse `run-bigpump.log`
    //: and then the NASTRAN deck and the section correctly refuses the deck three
    //: panels up while still captioning a hydraulic run from two clicks ago as
    //: the thing you just submitted. Falling back to the fixture is what the
    //: comment here always claimed happened; now it does.
    showFixture(
      `<span style="color:var(--warn);font-size:11.5px"><b>${esc(t.artifact || "that artifact")}</b>
   produced no solved state (${esc((t.outcome || "refused").replace(/_/g, " "))}),
   so there is nothing to place in this space &mdash; showing the shipped
   example instead. The refusal is above.</span>`,
    );
    return;
  }
  LIVE = live;
  MACH.right = null;
  MACH.overrideState = null;
  MACH.overrideLabel = null;
  GEO.sel = null;
  document
    .querySelectorAll(".tile")
    .forEach((x) => x.classList.remove("on"));
  //: the banner states what actually happened to *this* run. It used to say
  //: "and the case retrieval chose for it" unconditionally, which on a warned
  //: transfer described the opposite of what the pipeline did three panels
  //: above: retrieval found the case, the verifier warned, and the solver never
  //: touched it. The neighbour is still drawn -- seeing what was rejected is
  //: the point -- but it is labelled as rejected.
  $("#liverow").innerHTML =
    `<button class="geobtn" id="livereset">Show the shipped example</button>` +
    (live.usedArchive
      ? `<span style="color:var(--ok);font-size:11.5px">showing <b>${esc(live.id)}</b>
     &mdash; the artifact you just analysed, and the case retrieval chose for it</span>`
      : `<span style="color:var(--warn);font-size:11.5px">showing <b>${esc(live.id)}</b>
     &mdash; the artifact you just analysed, beside the case retrieval found and
     <b>the verifier refused</b>. It was not used as a starting point.</span>`);
  $("#livereset").onclick = () => showFixture();
  renderGeoAll();
}

//: from here down, the views ask these two for their subject instead of
//: reaching into VIZ directly, so one branch decides "live or fixture" and the
//: three panels can never disagree about which case they are showing.
function subjectPair() {
  return LIVE
    ? {
        query: LIVE,
        neighbour: LIVE.neighbour,
        distance: LIVE.distance,
        live: true,
      }
    : {
        query: VIZ.pair.query,
        neighbour: VIZ.pair.neighbour,
        distance: VIZ.pair.setup_distance,
        live: false,
      };
}
function subjectRace() {
  if (!LIVE || !LIVE.paths || !LIVE.paths.cold) return VIZ.race;
  const out = {};
  for (const k of ["cold", "nominal", "warm"]) {
    const p = LIVE.paths[k];
    if (!p) continue;
    //: `converged` travels with the count, because a path's length is the
    //: number of steps taken and says nothing about whether the last one
    //: arrived anywhere. Every caller that prints an iteration count has to be
    //: able to tell a result from a stall. `VIZ.race` already carries the flag,
    //: so the fixture and the live run answer the same question the same way.
    out[k] = {
      iterations: p.length - 1,
      converged: (LIVE.converged || {})[k] !== false,
      path_xyz: p.map((row) =>
        projectState(
          Object.fromEntries(
            VIZ.projection.transform.state_order.map((n, i) => [
              n,
              row[i],
            ]),
          ),
        ),
      ),
    };
  }
  return out;
}
const GEO = {
  mode: "archive",
  yaw: 0.62,
  pitch: 0.34,
  step: 0,
  spin: !REDUCED_MOTION,
  sel: null,
  bounds: null,
  raf: null,
  playing: false,
};

//: pressure ramp, dark-cool to hot. Not decoration: p1 is the manifold and p3
//: is the return line, so a tile that reads dark on the right is a case where
//: most of the pump's pressure was spent, which is what the eye should catch.
const RAMP = [
  [0, [22, 65, 63]],
  [0.33, [10, 107, 107]],
  [0.6, [0, 179, 179]],
  [0.8, [255, 180, 84]],
  [1, [255, 107, 94]],
];
function ramp(t) {
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < RAMP.length; i++) {
    if (t <= RAMP[i][0]) {
      const [a, ca] = RAMP[i - 1],
        [b, cb] = RAMP[i],
        u = (t - a) / (b - a || 1);
      return `rgb(${ca.map((v, k) => Math.round(v + (cb[k] - v) * u)).join(",")})`;
    }
  }
  return `rgb(${RAMP[RAMP.length - 1][1].join(",")})`;
}

//: orthographic yaw-then-pitch. Orthographic rather than perspective because
//: this is a map of a space, not a photograph of an object — a perspective
//: divide would make equal distances look unequal, which is the one thing a
//: picture about distance must not do.
function rot3(p) {
  const cy = Math.cos(GEO.yaw),
    sy = Math.sin(GEO.yaw);
  const cp = Math.cos(GEO.pitch),
    sp = Math.sin(GEO.pitch);
  const x = p[0],
    y = p[1],
    z = p[2];
  const x1 = x * cy + z * sy,
    z1 = z * cy - x * sy;
  return [x1, y * cp - z1 * sp, y * sp + z1 * cp];
}

//: the largest distance from the centre, not the largest coordinate. Rotation
//: preserves length, so a scale set from the radius fits at every viewing angle
//: — sizing from per-axis extents instead makes the cloud breathe as it spins.
function geoBounds() {
  const pts = VIZ.archive
    .map((a) => a.xyz)
    .concat(Object.values(subjectRace()).flatMap((r) => r.path_xyz));
  let m = 0;
  for (const p of pts) m = Math.max(m, Math.hypot(p[0], p[1], p[2]));
  return m || 1;
}

const VCX = 250,
  VCY = 180;
function screen(p) {
  const r = rot3(p),
    s = 166 / GEO.bounds;
  return [VCX + r[0] * s, VCY - r[1] * s, r[2]];
}

//: a triad rather than boxed axes: the three directions are principal
//: components, so their *orientation* is meaningful and their origin is not.
function triad() {
  const o = [455, 322],
    L = 30;
  return VIZ.projection.axes
    .map((ax, i) => {
      const v = [0, 0, 0];
      v[i] = 1;
      const r = rot3(v);
      const x = o[0] + r[0] * L,
        y = o[1] - r[1] * L;
      return `<line x1="${o[0]}" y1="${o[1]}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"
            stroke="#3a4a50" stroke-width="1.2"/>
      <text x="${x.toFixed(1)}" y="${(y - 3).toFixed(1)}" fill="#5d7076"
            font-size="9" text-anchor="middle">${ax.variance_pct.toFixed(1)}%</text>`;
    })
    .join("");
}

function dot(p, r, fill, op, extra) {
  const s = screen(p);
  return {
    z: s[2],
    svg: `<circle cx="${s[0].toFixed(1)}" cy="${s[1].toFixed(1)}"
r="${r}" fill="${fill}" opacity="${op}" ${extra || ""}/>`,
  };
}

function polyline(path, colour, upto) {
  const pts = path
    .slice(0, upto == null ? path.length : upto + 1)
    .map(screen);
  if (!pts.length) return "";
  const d = pts
    .map(
      (p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`,
    )
    .join(" ");
  const dots = pts
    .map(
      (p, i) =>
        `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}"
 r="${i === pts.length - 1 ? 4.2 : 2.4}" fill="${colour}"
 stroke="${i === pts.length - 1 ? "#0e1416" : "none"}" stroke-width="1"/>`,
    )
    .join("");
  return `<path d="${d}" fill="none" stroke="${colour}" stroke-width="1.8"
          opacity="0.95" stroke-linejoin="round"/>${dots}`;
}

const ARM = {
  cold: { c: "#8fa3a9", label: "cold — every unknown at zero" },
  nominal: { c: "#ffb454", label: "nominal — an engineer’s guess" },
  warm: { c: "#3ddc97", label: "warm — the retrieved state" },
};

function renderView() {
  if (!VIZ) return;
  const layers = [];
  const dim = GEO.mode !== "archive";

  for (const a of VIZ.archive) {
    const on = GEO.sel === a.id;
    layers.push(
      dot(
        a.xyz,
        on ? 5 : 2.6,
        on ? "#e6eef0" : a.relief_open ? "#ffb454" : "#00b3b3",
        on ? 1 : dim ? 0.16 : 0.62,
        on ? 'stroke="#00b3b3" stroke-width="1.5"' : "",
      ),
    );
  }
  //: the analysed case is drawn on top of the cloud in every mode -- it is the
  //: subject, and a subject that vanishes when you change tab is not one.
  if (LIVE && GEO.mode !== "race") {
    layers.push(
      dot(
        LIVE.neighbour.xyz,
        5.5,
        "#00b3b3",
        1,
        'stroke="#0e1416" stroke-width="1.5"',
      ),
    );
    layers.push(
      dot(
        LIVE.xyz,
        6,
        "#3ddc97",
        1,
        'stroke="#0e1416" stroke-width="1.5"',
      ),
    );
  }
  layers.sort((u, v) => u.z - v.z);
  let svg = layers.map((l) => l.svg).join("");

  if (GEO.mode === "pair") {
    const P = subjectPair();
    const q = screen(P.query.xyz),
      n = screen(P.neighbour.xyz);
    svg += `<line x1="${q[0].toFixed(1)}" y1="${q[1].toFixed(1)}"
            x2="${n[0].toFixed(1)}" y2="${n[1].toFixed(1)}"
            stroke="#3ddc97" stroke-width="1.4" stroke-dasharray="4 3"/>`;
    svg += `<circle cx="${n[0].toFixed(1)}" cy="${n[1].toFixed(1)}" r="6"
        fill="#00b3b3" stroke="#0e1416" stroke-width="1.5"/>
      <circle cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" r="6"
        fill="#3ddc97" stroke="#0e1416" stroke-width="1.5"/>
      <text x="${(n[0] + 9).toFixed(1)}" y="${(n[1] + 4).toFixed(1)}" fill="#8fa3a9"
        font-size="10.5" font-family="ui-monospace,monospace">${esc(P.neighbour.id)}</text>
      <text x="${(q[0] + 9).toFixed(1)}" y="${(q[1] + 4).toFixed(1)}" fill="#e6eef0"
        font-size="10.5" font-family="ui-monospace,monospace">${esc(P.query.id)}</text>`;
  }

  if (GEO.mode === "race") {
    const R = subjectRace();
    for (const k of ["cold", "nominal", "warm"])
      if (R[k]) svg += polyline(R[k].path_xyz, ARM[k].c, GEO.step);
  }

  $("#geoview").innerHTML = svg + triad();
}

function renderControls() {
  const m = GEO.mode;
  if (m === "race") {
    const R = subjectRace();
    const maxStep = Math.max(
      ...Object.values(R).map((r) => r.path_xyz.length - 1),
    );
    $("#georow").innerHTML =
      `<button class="geobtn" id="geoplay">${GEO.playing ? "Pause" : "Play"}</button>
 <button class="geobtn" id="georeset">Reset</button>
 <span style="color:var(--faint);font-size:11.5px">
   iteration <b style="color:var(--ink);font-family:var(--mono)">${Math.min(GEO.step, maxStep)}</b>
   of ${maxStep}</span>`;
    $("#geoplay").onclick = () => {
      GEO.playing = !GEO.playing;
      if (GEO.playing && GEO.step >= maxStep) GEO.step = 0;
      renderControls();
    };
    $("#georeset").onclick = () => {
      GEO.step = 0;
      GEO.playing = false;
      renderControls();
      renderView();
    };
    //: the count and its caveat live in one element on purpose -- `.geokey span`
    //: is an inline-flex row with a 5px gap, so a second child would be pushed
    //: away from the text it qualifies and render as "7 iterations , did not
    //: converge"
    $("#geokey").innerHTML = ["cold", "nominal", "warm"]
      .filter((k) => R[k])
      .map(
        (k) =>
          `<span><i style="background:${ARM[k].c}"></i>${esc(ARM[k].label)} &mdash;
  <b style="color:${R[k].converged === false ? "var(--refuse)" : "var(--ink)"}"
  >${R[k].iterations} iterations${
    R[k].converged === false ? ", did not converge" : ""
  }</b></span>`,
      )
      .join("");
  } else {
    $("#georow").innerHTML =
      `<button class="geobtn" id="geospin">${GEO.spin ? "Stop" : "Spin"}</button>
 <span style="color:var(--faint);font-size:11.5px">drag to rotate</span>`;
    $("#geospin").onclick = () => {
      GEO.spin = !GEO.spin;
      renderControls();
    };
    $("#geokey").innerHTML =
      `<span><i style="background:#00b3b3"></i>relief valve closed</span>
 <span><i style="background:#ffb454"></i>relief valve open</span>` +
      (m === "pair"
        ? `<span><i style="background:#3ddc97"></i>the query</span>`
        : "");
  }
  $("#geocap").innerHTML = CAPTION[m]();
  //: `#geoview`'s aria-label shipped as one fixed string describing only the
  //: default tab ("solved states of the archive, projected to three
  //: dimensions"), and nothing updated it when the tab changed -- so a screen
  //: reader kept describing the archive cloud after switching to the matched
  //: pair or the cold-vs-warm race, which is a different picture in the same
  //: element.
  $("#geoview").setAttribute("aria-label", GEOVIEW_ARIA_LABEL[m]);
}

//: one line per tab, matching what CAPTION says in prose -- kept short and
//: literal, since a screen reader gets no colour key and no caption text, only
//: this string and the SVG's drawn content.
const GEOVIEW_ARIA_LABEL = {
  archive: "solved states of the archive, projected to three dimensions",
  pair:
    "the analysed case and its retrieved neighbour, projected to the same " +
    "three dimensions",
  race:
    "the solver's path from each starting guess to the same answer, " +
    "projected to the same three dimensions",
};

const CAPTION = {
  archive: () => {
    const p = VIZ.projection;
    return `${VIZ.config.archive_size} solved cases, placed by where their answer landed.
Three axes carry <b>${p.top3_variance_pct}%</b> of the variance. Distances quoted
here are true seven-parameter distances, not screen distances.`;
  },
  pair: () => {
    const P = subjectPair(),
      g = pairGap(P);
    return `<b>${esc(P.query.id)}</b> &rarr; <b>${esc(P.neighbour.id)}</b> at distance
<b>${(+P.distance).toFixed(3)}</b>. Solved states differ by
<b>${g.dp.toFixed(1)} bar</b> and <b>${Math.round(g.dw)} rev/min</b>.`;
  },
  race: () => {
    const R = subjectRace();
    const n = (k) => (R[k] ? R[k].iterations : "&mdash;");
    //: "same answer" is a claim about arms that both ran and both converged.
    //: On a warned transfer there is no warm arm to agree with anything, and
    //: on a case where the flat start stalls there is a count that is not a
    //: result. The sentence used to assert agreement in both situations.
    const stalled = ["cold", "nominal", "warm"].filter(
      (k) => R[k] && R[k].converged === false,
    );
    const tail = !R.warm
      ? ` &mdash; the warm arm was not run: the transfer was warned and left
    standing, so the solver started from the nominal guess instead.`
      : stalled.length
        ? ` &mdash; same answer, from the arms that got one: the
    <b>${stalled.join(" and ")}</b> start did not converge at all.`
        : " &mdash; same answer.";
    return `Only the starting point differs. Cold <b>${n("cold")}</b>,
nominal <b>${n("nominal")}</b>, warm <b>${n("warm")}</b> iterations${tail}`;
  },
};

/* --- the contact sheet ------------------------------------------------- */
//: a schematic, not a rendering. The circuit this solves is a lumped hydraulic
//: network — there is no geometry in the model, so drawing geometry would be
//: inventing it. An Amesim-shaped sketch is both honest and the vocabulary the
//: audience already reads: pipe colour is solved pressure, ring fill is solved
//: shaft speed, and every number in it came out of the solver.
let PSCALE = 1;
function schematic(c, w) {
  const s = c.solution,
    p = c.params;
  const col = (v) => ramp(v / PSCALE);
  //: `area` used to be accepted and dropped, so every tile drew the same
  //: fixed-width line here regardless of the valve's actual flow area --
  //: making the section copy's "bore is the valve's real flow area" true of
  //: the 3D view (`machineParts` already uses `bore(area)`) but not of these
  //: tiles. Same function, same physical variable, so a wide-open valve and a
  //: near-shut one now read as visibly different bores here too, not only in
  //: the 3D model.
  const branch = (Y, p2, p3, w_, area) => {
    const spd = Math.min(1, Math.abs(w_) / 2600);
    const circ = 2 * Math.PI * 7.5;
    const valveWidth = (bore(area) * 8).toFixed(2);
    return `
<line x1="30" y1="${Y}" x2="43" y2="${Y}" stroke="${col(s.p1)}" stroke-width="2.6"/>
<path d="M43 ${Y - 5} L47 ${Y - 1.6} M43 ${Y + 5} L47 ${Y + 1.6}" stroke="#5d7076"
      stroke-width="1.5" fill="none"/>
<line x1="47" y1="${Y}" x2="64" y2="${Y}" stroke="${col(p2)}" stroke-width="${valveWidth}"/>
<circle cx="72" cy="${Y}" r="7.5" fill="#121b1e" stroke="#3a4a50" stroke-width="1.2"/>
<circle cx="72" cy="${Y}" r="7.5" fill="none" stroke="#3ddc97" stroke-width="2"
        stroke-dasharray="${(circ * spd).toFixed(1)} ${circ.toFixed(1)}"
        transform="rotate(-90 72 ${Y})" opacity="0.9"/>
<line x1="80" y1="${Y}" x2="97" y2="${Y}" stroke="${col(p3)}" stroke-width="2.6"/>
<path d="M97 ${Y} L104 ${Y} M100 ${Y + 4} L108 ${Y + 4}" stroke="#3a4a50"
      stroke-width="1.4" fill="none"/>`;
  };
  const reliefOn = c.relief_open;
  return `<svg viewBox="0 0 116 84" width="${w || "100%"}" role="img">
<circle cx="11" cy="42" r="6.5" fill="#121b1e" stroke="#3a4a50" stroke-width="1.2"/>
<path d="M8 42 L14 42 M11 39 L11 45" stroke="#5d7076" stroke-width="1.2"/>
<line x1="17.5" y1="42" x2="30" y2="42" stroke="${col(s.p1)}" stroke-width="2.6"/>
<line x1="30" y1="18" x2="30" y2="66" stroke="${col(s.p1)}" stroke-width="3.4"/>
<line x1="30" y1="66" x2="30" y2="72" stroke="${reliefOn ? "#ffb454" : "#243237"}"
    stroke-width="2.2"/>
<rect x="26" y="72" width="8" height="6" rx="1"
    fill="${reliefOn ? "#ffb454" : "#1a2529"}" stroke="#3a4a50" stroke-width="1"/>
${branch(18, s.p2a, s.p3a, s.w_a, p.A_valve_a)}
${branch(66, s.p2b, s.p3b, s.w_b, p.A_valve_b)}
</svg>`;
}

/* --- the runs that died --------------------------------------------------
//: Failures cannot go in the cloud above: that view is drawn in solution
//: space and a failed run has no solution. They are placed here on the one
//: axis that needs no projection at all -- true Euclidean distance in the
//: normalised parameter space retrieval actually searches -- so nothing about
//: this strip is approximate. The nearest *solved* case is drawn on the same
//: axis, because a distance means nothing without the scale beside it.
*/
function normParams(p) {
  const B = VIZ.param_bounds;
  return VIZ.param_names.map(
    (k) => (p[k] - B[k][0]) / (B[k][1] - B[k][0]),
  );
}
function paramDistance(a, b) {
  const x = normParams(a),
    y = normParams(b);
  return Math.hypot(...x.map((v, i) => v - y[i]));
}

function renderFailures() {
  if (!VIZ.failures || !VIZ.failures.length) {
    $("#failwrap").innerHTML = "";
    return;
  }
  const P = subjectPair();
  const rows = VIZ.failures
    .map((f) => ({ ...f, d: paramDistance(P.query.params, f.params) }))
    .sort((a, b) => a.d - b.d);
  const near = rows[0];
  const good = P.distance;
  const max = Math.max(rows[rows.length - 1].d, good) * 1.12;
  const W = 520,
    L = 8,
    R = 96,
    y = 30;
  const px = (d) => L + (d / max) * (W - L - R);

  const marks = rows
    .map(
      (f) =>
        `<g><line x1="${px(f.d).toFixed(1)}" y1="${y - 7}" x2="${px(f.d).toFixed(1)}" y2="${y + 7}"
  stroke="#ff6b5e" stroke-width="2"/>
<title>${esc(f.id)} — ${esc(f.status)} — distance ${f.d.toFixed(3)}</title></g>`,
    )
    .join("");

  $("#failwrap").innerHTML = `
<h3>The runs that died <span class="failn">${VIZ.failures.length} of
${VIZ.config.archive_size + VIZ.failures.length}</span></h3>
<svg viewBox="0 0 ${W} 58" width="100%" role="img"
   aria-label="failed runs by true distance from the current case">
<line x1="${L}" y1="${y}" x2="${W - R}" y2="${y}" stroke="#243237" stroke-width="1"/>
<g><line x1="${px(good).toFixed(1)}" y1="${y - 9}" x2="${px(good).toFixed(1)}" y2="${y + 9}"
     stroke="#3ddc97" stroke-width="2.5"/>
  <title>${esc(P.neighbour.id)} — the retrieved case — distance ${good.toFixed(3)}</title></g>
${marks}
<text x="${L}" y="${y + 24}" fill="#5d7076" font-size="10">0 &mdash; identical setup</text>
<text x="${(W - R).toFixed(0)}" y="${y + 24}" fill="#5d7076" font-size="10"
      text-anchor="end">${max.toFixed(2)}</text>
<text x="${(W - R + 8).toFixed(0)}" y="${y - 2}" fill="#3ddc97" font-size="10">retrieved</text>
<text x="${(W - R + 8).toFixed(0)}" y="${y + 11}" fill="#ff6b5e" font-size="10">failed</text>
</svg>
<div class="failnote">
Nearest failed run <b>${esc(near.id)}</b> (<b>${esc(near.status)}</b>) at
<b>${near.d.toFixed(3)}</b>, against <b>${good.toFixed(3)}</b> to the retrieved
case. Failures have no solved state, so they have no 3D model and no place in
the cloud &mdash; shown here as setups only. Context, not a decision.
</div>`;
}

//: The four numbers under the contact sheet describe *whichever pair the
//: section is currently showing* -- and once an artifact has been analysed that
//: is the analysed one, not the fixture.
//:
//: It used to always read `VIZ.pair`/`VIZ.race`, the exemplar shipped in
//: viz_results.json, because `adoptTrace` re-renders the view and the machine
//: panel but never the sheet. So the banner said "showing run-tidy.log -- the
//: artifact you just analysed" while the row beneath it quoted 11 -> 4 from a
//: different case entirely, against the pipeline's own 8 -> 3. Two panels on
//: one screen disagreeing about the same run is worse than either number being
//: wrong, because it makes both untrustworthy.
//: Every cell here is a number the pipeline reported, or a word saying it did
//: not report one. Both used to be printed the same way: on a warned transfer
//: `solve` carries no `warm_iterations` and no `agreement`, and this template
//: interpolated them straight, so the panel read "iterations 10 -> undefined"
//: and "agreement NaN bar" one click from the front page.
function renderGeoNums() {
  if (LIVE) {
    const gap = stateGap(LIVE.solution, LIVE.neighbour.solution);
    const it = LIVE.iterations || {},
      ok = LIVE.converged || {};
    const none = (w) =>
      `<span style="color:var(--warn);font-size:12px">${w}</span>`;
    //: a stalled arm reports the iteration it gave up on. Printing that as a
    //: baseline reads as a result, so it is marked rather than shown bare.
    const count = (k) =>
      it[k] === undefined
        ? none("not run")
        : ok[k] === false
          ? `${it[k]}<span style="color:var(--refuse)">*</span>`
          : `${it[k]}`;
    const stalled = ["cold", "warm"].some((k) => ok[k] === false);
    $("#geonums").innerHTML =
      `
<div>setup distance<b>${(+LIVE.distance).toFixed(3)}</b>true, 7 parameters</div>
<div>state gap<b>${gap.dp.toFixed(1)} bar</b>${Math.round(gap.dw)} rev/min</div>
<div>iterations<b>${count("cold")} &rarr; ${count("warm")}</b>cold &rarr; warm${
  stalled
    ? ' &middot; <span style="color:var(--refuse)">*did not converge</span>'
    : ""
}</div>` +
      (LIVE.agreement === undefined
        ? `<div>agreement<b>${none("not checked")}</b>${
            LIVE.usedArchive
              ? "no converged baseline"
              : "the archive was not used"
          }</div>`
        : `<div>agreement<b>${(+LIVE.agreement).toExponential(1)}</b>bar, vs ${esc(
            LIVE.agreementAgainst || "baseline",
          )}</div>`);
    return;
  }
  const p = VIZ.pair,
    r = VIZ.race;
  $("#geonums").innerHTML = `
<div>setup distance<b>${p.setup_distance.toFixed(3)}</b>true, 7 parameters</div>
<div>state gap<b>${p.state_gap_bar.toFixed(1)} bar</b>${Math.round(p.state_gap_rpm)} rev/min</div>
<div>iterations<b>${r.cold.iterations} &rarr; ${r.warm.iterations}</b>cold &rarr; warm</div>
<div>agreement<b>${(+r.warm.agreement_vs_cold.max_dp_bar).toExponential(1)}</b>bar</div>`;
}

//: the colour ramp's ceiling -- everyone with `p1` at or above `PSCALE` reads
//: identically at the hot end of the ramp, so this has to cover whichever
//: case is actually on screen. It used to be computed once, here, at boot,
//: and never again: `adoptTrace` re-rendered the view, the machine panel and
//: the contact sheet's numbers after a live analyse, but not this. A case
//: whose solved `p1` exceeds the fixture's own ceiling (258 bar; `p_crack`
//: alone reaches 260) rendered every pipe at the top of the ramp and was
//: visually indistinguishable from any other high-pressure case -- reachable
//: any time the relief valve is cracked. Split out from `renderTiles()`
//: rather than just calling that function again on every live analyse:
//: `renderTiles()` rebuilds `#tiles` from scratch and does not know about
//: `GEO.sel`, so calling it again would have silently cleared whichever tile
//: was hand-picked.
function recomputePScale() {
  const P0 = subjectPair();
  PSCALE = Math.max(
    ...VIZ.tiles.concat([P0.neighbour]).map((t) => t.solution.p1),
    P0.query.solution.p1,
  );
}

function renderTiles() {
  recomputePScale();
  $("#sheetcn").innerHTML =
    `${VIZ.config.n_tiles} of ${VIZ.config.archive_size}, chosen to span the cloud &middot;
pipe colour is solved pressure, ring fill is solved shaft speed`;
  $("#tiles").innerHTML = VIZ.tiles
    .map(
      (t) =>
        `<button class="tile" data-id="${esc(t.id)}" title="${esc(t.id)}">
 ${schematic(t)}
 <div class="tl"><span>${esc(t.id.replace("sweep-", ""))}</span>
   <span>${Math.round(t.solution.p1)}&#8202;bar</span></div>
</button>`,
    )
    .join("");
  $("#tiles").onclick = (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    const id = b.dataset.id;
    GEO.sel = GEO.sel === id ? null : id;
    document
      .querySelectorAll(".tile")
      .forEach((t) => t.classList.toggle("on", t.dataset.id === GEO.sel));
    if (GEO.sel) {
      MACH.right = VIZ.tiles.find((t) => t.id === GEO.sel) || null;
    }
    renderMachPanel();
    if (GEO.sel && GEO.mode !== "archive") setMode("archive");
    else renderView();
  };
  renderGeoNums();
}

function setMode(m) {
  GEO.mode = m;
  GEO.playing = false;
  if (m === "race") GEO.step = 0;
  //: scoped to `#geotabs` -- `.geotab` is shared with the stepper's arm
  //: buttons in `#steparms`, which carry `data-arm` rather than `data-mode`.
  //: An unscoped `document.querySelectorAll('.geotab')` matched both groups,
  //: so `t.dataset.mode === m` was false for every stepper button (they have
  //: no `data-mode` at all) and every one of them lost its `.on` highlight --
  //: and, once aria-pressed was added, its pressed state -- the moment this
  //: page's *other* tab group was clicked. `STEPPER.arm` itself was untouched,
  //: so the trajectory kept stepping correctly; only the highlight lied about
  //: which arm was selected.
  $("#geotabs")
    .querySelectorAll(".geotab")
    .forEach((t) => {
      const on = t.dataset.mode === m;
      t.classList.toggle("on", on);
      t.setAttribute("aria-pressed", on);
    });
  renderControls();
  renderView();
}

//: this page runs three uncapped rAF loops for its lifetime -- the spinning
//: cloud, the two 3D machine views, the flow animation -- and none of them
//: used to know whether anyone could see them. Measured: ~8ms/frame rebuilding
//: both machine views (178 SVG nodes each), ~2.7ms spinning the cloud (403
//: nodes), ~1ms for the flow view -- roughly 12ms of main-thread work every
//: frame, whether the section is on screen, scrolled past, or the tab is in
//: the background. `state.visible` tracks whether the loop's own section
//: currently has a layout box on screen; the timers (`yaw`, `_t`, `step`)
//: still advance while it doesn't, so the picture is still where it should be
//: the instant it scrolls back into view -- only the expensive SVG rebuild is
//: skipped while nothing could show it.
function trackVisible(id, state) {
  const el = document.getElementById(id);
  if (!el || !("IntersectionObserver" in window)) {
    state.visible = true;
    return;
  }
  state.visible = false;
  new IntersectionObserver(
    (entries) => {
      state.visible = entries[0].isIntersecting;
    },
    { threshold: 0 },
  ).observe(el);
}

function geoTick() {
  let dirty = false;
  if (GEO.spin && GEO.mode !== "race") {
    GEO.yaw += 0.0032;
    dirty = true;
  }
  if (GEO.playing) {
    GEO._t = (GEO._t || 0) + 1;
    if (GEO._t % 28 === 0) {
      const maxStep = Math.max(
        ...Object.values(subjectRace()).map((r) => r.path_xyz.length - 1),
      );
      if (GEO.step < maxStep) {
        GEO.step++;
        dirty = true;
        renderControls();
      } else {
        GEO.playing = false;
        renderControls();
      }
    }
  }
  if (dirty && GEO.visible) renderView();
  GEO.raf = requestAnimationFrame(geoTick);
}

function geoDrag() {
  const el = $("#geoview");
  let last = null;
  el.addEventListener("pointerdown", (e) => {
    last = [e.clientX, e.clientY];
    GEO.spin = false;
    el.classList.add("drag");
    el.setPointerCapture(e.pointerId);
    renderControls();
  });
  el.addEventListener("pointermove", (e) => {
    if (!last) return;
    GEO.yaw += (e.clientX - last[0]) * 0.008;
    GEO.pitch = Math.max(
      -1.35,
      Math.min(1.35, GEO.pitch + (e.clientY - last[1]) * 0.008),
    );
    last = [e.clientX, e.clientY];
    renderView();
  });
  const up = () => {
    last = null;
    el.classList.remove("drag");
  };
  el.addEventListener("pointerup", up);
  el.addEventListener("pointercancel", up);
}

async function geoBoot() {
  const res = await fetch("/api/viz");
  if (!res.ok) throw new Error("viz unavailable");
  VIZ = await res.json();
  GEO.bounds = geoBounds();
  const p = VIZ.projection;
  $("#geosub").innerHTML =
    `Where the solved states sit, and why a neighbour is a good place to start.`;
  $("#geotabs").onclick = (e) => {
    const b = e.target.closest("button");
    if (b) setMode(b.dataset.mode);
  };
  renderTiles();
  renderFailures();
  renderControls();
  renderView();
  geoDrag();
  trackVisible("geo", GEO);
  GEO.raf = requestAnimationFrame(geoTick);
  machBoot();
}

/* --- the machine ---------------------------------------------------------
//: A 3D view of the circuit being solved: reservoir, pump, manifold block,
//: relief valve, two feed lines through their orifices, two motors, two
//: returns. Hand-built primitives, but really rendered now: WebGL through
//: three.js, a perspective camera and three lights per panel, so the depth
//: you read is depth rather than a fixed projection faking it. three.js is
//: vendored into dejasolve/static/vendor/ — the "no CDN" promise this comment used
//: to make is now enforced by the server instead of asserted here.
//:
//: **Say what this is before anyone asks.** The model is lumped: it has seven
//: unknowns and no geometry, so the *layout* here is illustrative and nothing
//: about pipe length or routing was simulated. What is solved is what drives
//: it — pipe colour is the solved pressure at that node, the orifice bore is
//: the valve's real flow area, the relief valve stands open only when the
//: solved regime says it does, and each motor turns at its own solved speed.
//: Drawing a mesh would have claimed the thing §6h is careful never to claim;
//: drawing the circuit claims exactly what the solver actually computed.
*/
const MACH = {
  yaw: 0.72,
  pitch: 0.42,
  //: a multiplier on the fit distance each scene computes, not an absolute
  //: distance -- so zoom means the same thing in both panels even though each
  //: fits its own panel width, and it survives a rebuild that changes extent.
  zoom: 1,
  //: drag velocity, carried for a few frames after release so a flick coasts.
  vyaw: 0,
  vpitch: 0,
  t0: performance.now(),
  raf: null,
  right: null,
  spin: !REDUCED_MOTION,
};

//: bore in model units. Diameter, not area, scales with sqrt(A) — an orifice
//: twice the flow area is sqrt(2) wider, and drawing it twice as wide would
//: misstate the one parameter this picture puts on screen.
const BORE_MAIN = 0.4,
  A_REF = 10.0;
const bore = (a) => 0.13 + 0.3 * Math.sqrt(Math.max(a, 0) / A_REF);

function machineParts(c) {
  const s = c.solution,
    p = c.params,
    parts = [];
  const P = (v) => ramp(v / PSCALE);
  const RES_Y = -6.4;

  //: reservoir and the suction line up to the pump. The tank spans x -12.4..7.9
  //: because that is what it has to span: the suction leg drops at x=-11 and both
  //: return legs at x=7.4, and a tank narrower than its own plumbing leaves three
  //: pipes ending in mid-air. It used to be 15.6 wide and centred at -0.6, so the
  //: suction leg hung 2.6 units clear of it.
  parts.push({
    t: "box",
    c: [-2.25, RES_Y - 0.7, 0],
    s: [20.3, 1.5, 5.4],
    col: "#3d565e",
  });
  parts.push({
    t: "pipe",
    pts: [
      [-11, RES_Y - 0.4, 0],
      [-11, -0.6, 0],
    ],
    r: BORE_MAIN,
    col: "#415a63",
    flow: true,
    flowSpeed: 0.6,
  });
  // pump, and the supply line into the manifold
  parts.push({
    t: "motor",
    c: [-11, 0, 0],
    len: 1.5,
    r: 1.15,
    col: "#40575f",
    w: 0,
    axis: "y",
  });
  parts.push({
    t: "pipe",
    pts: [
      [-11, 0.6, 0],
      [-11, 1.85, 1.25],
      [-8.9, 1.85, 1.25],
      [-8.9, 0, 1.25],
      [-7.5, 0, 1.25],
    ],
    r: BORE_MAIN,
    col: P(s.p1),
    flow: true,
    flowSpeed: Math.max(0.2, (s.p1 || 0) / 90),
  });
  // the manifold block itself is at p1
  parts.push({
    t: "box",
    c: [-7.0, 0, 0],
    s: [1.9, 6.4, 3.4],
    col: P(s.p1),
    edge: true,
  });

  // relief valve: a stub down to tank, open only when the solved regime says so
  parts.push({
    t: "pipe",
    pts: [
      [-7.0, -3.2, 0],
      [-7.0, -4.4, 0],
    ],
    r: 0.26,
    col: c.relief_open ? "#ffb454" : "#415a63",
    flow: !!c.relief_open,
    flowSpeed: 1.2,
  });
  parts.push({
    t: "box",
    c: [-7.0, -4.9, 0],
    s: [1.2, 1.0, 1.2],
    col: c.relief_open ? "#ffb454" : "#35494f",
    edge: true,
  });
  parts.push({
    t: "pipe",
    pts: [
      [-7.0, -5.4, 0],
      [-7.0, RES_Y - 0.2, 0],
    ],
    r: 0.22,
    col: c.relief_open ? "#ffb454" : "#415a63",
    flow: !!c.relief_open,
    flowSpeed: 1.2,
  });

  const branch = (Y, Z, p2, p3, w, area) => {
    parts.push({
      t: "pipe",
      pts: [
        [-6.2, Y, Z * 0.46],
        [-4.6, Y, Z],
        [-2.2, Y, Z],
      ],
      r: BORE_MAIN,
      col: P(s.p1),
      flow: true,
      flowSpeed: Math.max(0.15, (s.p1 || 0) / 100),
    });
    parts.push({
      t: "pipe",
      pts: [
        [-2.2, Y, Z],
        [-1.2, Y, Z],
      ],
      r: bore(area),
      col: "#7d9198",
      flow: true,
      flowSpeed: 0.9,
    });
    parts.push({
      t: "pipe",
      pts: [
        [-1.2, Y, Z],
        [2.35, Y, Z],
      ],
      r: BORE_MAIN,
      col: P(p2),
      flow: true,
      flowSpeed: Math.max(
        0.15,
        Math.sqrt(Math.max(0, (s.p1 || 0) - p2)) / 7,
      ),
    });
    parts.push({
      t: "motor",
      c: [2.9, Y, Z],
      len: 1.6,
      r: 1.5,
      col: "#3a5058",
      w: w,
      axis: "x",
    });
    parts.push({
      t: "pipe",
      pts: [
        [3.45, Y, Z],
        [6.6, Y, Z],
        [7.4, Y, Z * 0.45],
        [7.4, RES_Y - 0.4, Z * 0.45],
      ],
      r: BORE_MAIN,
      col: P(p3),
      flow: true,
      flowSpeed: Math.max(0.15, Math.sqrt(Math.max(0, p3)) / 6),
    });
  };
  branch(2.1, 2.5, s.p2a, s.p3a, s.w_a, p.A_valve_a);
  branch(-2.1, -2.5, s.p2b, s.p3b, s.w_b, p.A_valve_b);
  return parts;
}

/* --- where the flow goes --------------------------------------------------
//: The other two views draw *pressure* -- colour in the schematic, colour in
//: the 3D model. Neither can show where the oil actually goes, and on this
//: circuit that is not a detail: the relief valve is a leg that carries real
//: flow and does no work at all, so a case with it cracked open is spending
//: part of every pump revolution pushing oil back to tank.
//:
//: Every number here is `model.flows` on the converged state, which is the
//: same arithmetic `residual` does. That matters for honesty: at convergence
//: `pump = relief + a + b` to 1e-8, so dots cannot appear or vanish at a
//: junction, because the physics says they do not.
//:
//: **Spacing, not speed.** The model is lumped and has no pipe area, so there
//: is no velocity to draw. Dot spacing is litres per minute; every dot travels
//: at the same rate.
*/
const FLOW = { t0: performance.now(), raf: null, data: null };

//: one polyline, with dots spaced by flow. `q` is L/min.
function flowLeg(pts, q, colour, tms, width) {
  const seg = [];
  let total = 0;
  for (let i = 1; i < pts.length; i++) {
    const dx = pts[i][0] - pts[i - 1][0],
      dy = pts[i][1] - pts[i - 1][1];
    const l = Math.hypot(dx, dy);
    seg.push([pts[i - 1], pts[i], l]);
    total += l;
  }
  const line = `<polyline points="${pts.map((p) => p.join(",")).join(" ")}"
fill="none" stroke="${colour}" stroke-width="${width || 5}"
stroke-linecap="round" stroke-linejoin="round" opacity="0.34"/>`;
  if (!(q > 1e-6)) return line;

  // spacing is inversely proportional to flow, clamped so a trickle does not
  // produce one dot per kilometre and a torrent does not produce a solid bar
  const spacing = Math.max(9, Math.min(90, 260 / q));
  const speed = 34; // px/s, the same for every leg
  const off = ((tms / 1000) * speed) % spacing;
  let out = line;
  for (let d = off; d < total; d += spacing) {
    let acc = 0,
      k = 0;
    while (k < seg.length && acc + seg[k][2] < d) {
      acc += seg[k][2];
      k++;
    }
    if (k >= seg.length) break;
    const f = (d - acc) / seg[k][2];
    const x = seg[k][0][0] + (seg[k][1][0] - seg[k][0][0]) * f;
    const y = seg[k][0][1] + (seg[k][1][1] - seg[k][0][1]) * f;
    out += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.5"
        fill="${colour}"/>`;
  }
  return out;
}

function renderFlow(tms) {
  const d = FLOW.data;
  if (!d) return;
  const f = d.flows,
    s = d.solution,
    open = d.relief_open;
  const TANK = 232,
    teal = "#00b3b3",
    warn = "#ffb454",
    dim = "#3a4a50";
  const YA = 62,
    YB = 150,
    XM = 128;
  const g = [];

  // reservoir
  g.push(`<rect x="26" y="${TANK}" width="418" height="12" rx="3"
      fill="#162226" stroke="#243237"/>`);
  // suction and pump
  g.push(
    flowLeg(
      [
        [52, TANK],
        [52, 150],
      ],
      f.pump,
      dim,
      tms,
      5,
    ),
  );
  g.push(`<circle cx="52" cy="140" r="13" fill="#121b1e" stroke="#3a4a50" stroke-width="1.5"/>
    <path d="M45 140 L59 140 M52 133 L52 147" stroke="#5d7076" stroke-width="1.5"/>
    <text x="52" y="170" fill="#5d7076" font-size="10"
          font-family="ui-monospace,monospace" text-anchor="middle">pump</text>`);
  // pump -> manifold
  g.push(
    flowLeg(
      [
        [52, 127],
        [52, 36],
        [XM, 36],
        [XM, YA],
      ],
      f.pump,
      teal,
      tms,
      6,
    ),
  );
  // the manifold rail
  g.push(
    flowLeg(
      [
        [XM, YA],
        [XM, YB],
      ],
      f.valve_b + f.relief,
      teal,
      tms,
      6,
    ),
  );
  // relief leg: the one that does no work
  g.push(
    flowLeg(
      [
        [XM, YB],
        [XM, 196],
        [92, 196],
        [92, TANK],
      ],
      f.relief,
      open ? warn : dim,
      tms,
      5,
    ),
  );
  g.push(`<rect x="${XM - 9}" y="188" width="18" height="14" rx="2"
      fill="${open ? warn : "#1a2529"}" stroke="#3a4a50" stroke-width="1.2"/>
    <text x="${XM + 16}" y="199" fill="${open ? warn : "#5d7076"}" font-size="10"
          font-family="ui-monospace,monospace">relief ${open ? "OPEN" : "shut"}</text>`);

  [
    [YA, "a", f.valve_a, s.w_a],
    [YB, "b", f.valve_b, s.w_b],
  ].forEach(([Y, tag, q, w]) => {
    g.push(
      flowLeg(
        [
          [XM, Y],
          [186, Y],
        ],
        q,
        teal,
        tms,
        5,
      ),
    );
    g.push(`<path d="M186 ${Y - 7} L194 ${Y - 2} M186 ${Y + 7} L194 ${Y + 2}"
        stroke="#7d9198" stroke-width="1.8" fill="none"/>
      <text x="190" y="${Y - 13}" fill="#5d7076" font-size="9.5"
            font-family="ui-monospace,monospace" text-anchor="middle">valve ${tag}</text>`);
    g.push(
      flowLeg(
        [
          [194, Y],
          [248, Y],
        ],
        q,
        teal,
        tms,
        5,
      ),
    );
    const spd = Math.min(1, Math.abs(w) / 2600),
      circ = 2 * Math.PI * 13;
    g.push(`<circle cx="262" cy="${Y}" r="13" fill="#121b1e" stroke="#3a4a50" stroke-width="1.5"/>
      <circle cx="262" cy="${Y}" r="13" fill="none" stroke="#3ddc97" stroke-width="3"
        stroke-dasharray="${(circ * spd).toFixed(1)} ${circ.toFixed(1)}"
        transform="rotate(-90 262 ${Y})"/>
      <text x="262" y="${Y - 19}" fill="#5d7076" font-size="9.5"
        font-family="ui-monospace,monospace" text-anchor="middle">${Math.round(w)} rev/min</text>`);
    g.push(
      flowLeg(
        [
          [275, Y],
          [352, Y],
          [352, TANK],
        ],
        q,
        teal,
        tms,
        5,
      ),
    );
  });

  $("#flowview").innerHTML = g.join("");
}

function adoptFlow(t) {
  const s = t && t.solve;
  if (!(s && s.flows && s.solution)) {
    FLOW.data = null;
    $("#flow").style.display = "none";
    return;
  }
  $("#flow").style.display = "";
  FLOW.data = {
    flows: s.flows,
    solution: s.solution,
    relief_open: !!(s.regime && s.regime.relief_open),
  };
  const f = s.flows;
  const wasted = 100 * f.power_wasted_share;
  $("#flownums").innerHTML = `
<div>pump delivers<b>${f.pump.toFixed(1)}</b>L/min</div>
<div>through shaft a<b>${f.valve_a.toFixed(1)}</b>L/min &middot; ${f.power_a_kw.toFixed(2)} kW</div>
<div>through shaft b<b>${f.valve_b.toFixed(1)}</b>L/min &middot; ${f.power_b_kw.toFixed(2)} kW</div>
<div>dumped by the relief<b style="color:${f.relief > 1e-6 ? "var(--warn)" : "var(--dim)"}">${f.relief.toFixed(1)}</b>L/min &middot; ${f.power_relief_kw.toFixed(2)} kW</div>`;
  $("#flowcap").innerHTML =
    f.relief > 1e-6
      ? `The relief valve is carrying <b>${f.relief.toFixed(1)} L/min</b> straight back
 to tank at <b>${Math.round(s.solution.p1)} bar</b> &mdash; <b>${wasted.toFixed(0)}%</b>
 of this case's hydraulic power, doing no work. That is in the solved answer,
 not an estimate: at convergence pump = relief + a + b to 1e-8 L/min.`
      : `The relief valve is shut, so every litre the pump delivers reaches a motor.
 Flow balances to 1e-8 L/min at every node &mdash; the dots cannot appear or
 vanish at a junction because the physics says they do not.`;
}

function flowTick() {
  //: frozen at 0 under reduced motion, same reasoning as machTick's `t`: the
  //: dots along each leg are the only moving part of this view, and this is
  //: their entire time source.
  if (FLOW.visible)
    renderFlow(REDUCED_MOTION ? 0 : performance.now() - FLOW.t0);
  FLOW.raf = requestAnimationFrame(flowTick);
}

let FLOW_PARTICLES_ON = true;
(() => {
  const el = $("#flowparticles");
  if (!el) return;
  FLOW_PARTICLES_ON = el.checked;
  el.addEventListener("change", () => {
    FLOW_PARTICLES_ON = el.checked;
    //: `THREE_D` is still in its temporal dead zone while this IIFE runs, but the
    //: handler does not fire until long after the module is built.
    THREE_D.setFlowParticles(FLOW_PARTICLES_ON);
  });
})();

const THREE_D = (() => {
  const scenes = new Map();
  const RPM_SLOW = 0.0004;
  //: dots per unit of pipe, not dots per pipe. A fixed three-per-pipe put the
  //: same three dots on the 0.6-long relief stub and on the 12-long return leg,
  //: so the long legs read as empty and the short ones as a clot.
  const FLOW_PER_UNIT = 1.15;
  const FLOW_MIN = 3;
  //: fraction of the bore. Small enough that the dot is clearly *inside* a tube
  //: rather than a bead threaded onto it -- at half the bore they bulged through
  //: the wall and the whole run read as a string of pearls instead of flow.
  const FLOW_DOT_R = 0.3;
  //: the camera frames whatever `build` actually produced. Nothing here knows
  //: the circuit's extent up front -- bore, tank width and leg routing all move
  //: with the case -- so `_frame` measures the built group and fits to that.
  //: The previous hardcoded centre (-1.4, -2.3, 0) was ~0.8 off in x and left
  //: the model sitting left of centre in both panels.
  const FIT_MARGIN = 1.16;

  function shade(hex, f) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex);
    let c;
    if (m) c = [0,2,4].map(i => parseInt(m[1].substr(i,2),16));
    else { const n = /rgb\((\d+),(\d+),(\d+)\)/.exec(hex); if(!n) return hex;
           c = [+n[1],+n[2],+n[3]]; }
    return `rgb(${c.map(v => Math.max(0, Math.min(255, Math.round(v*f)))).join(',')})`;
  }

  //: `setStyle`, not the three-number constructor. three manages colour spaces:
  //: a CSS string is decoded from sRGB into the linear working space, but three
  //: raw floats are taken to be linear already. This used to hand sRGB values in
  //: through the float path, so every colour it produced came out visibly
  //: brighter than the identical colour built from the same string.
  //:
  //: That is not cosmetic. Materials are *created* from strings and *updated*
  //: through here, so a panel changed appearance the moment anything recoloured
  //: it without rebuilding -- stepping the solver relit the whole machine, and
  //: the reservoir flipped between a dark slab and a pale one for no reason the
  //: physics could explain. `setStyle` handles "#rrggbb" and the "rgb(r,g,b)"
  //: that `shade` returns, both in sRGB, so build and update now agree.
  //: A metal with nothing to reflect is black. Every material here carries some
  //: metalness, and with no environment the renderer has no incident radiance to
  //: sample -- which is why the motors read as featureless dark drums and the
  //: glass pipes had no sheen at all no matter how far the lights were pushed.
  //:
  //: A studio HDRI would be the usual answer and is out of the question: it is a
  //: multi-megabyte asset and this page's whole point is that it ships whole. A
  //: 32x128 canvas gradient run through PMREM costs nothing, is generated at
  //: boot, and buys the one thing that was missing -- a bright sky above and a
  //: dark floor below, so curved surfaces pick up a gradient across their length
  //: and stop reading as flat fills. PMREMGenerator is core three, not examples/.
  function makeEnvironment(renderer) {
    //: the gradient is painted into a sphere and PMREM'd `fromScene`, not handed
    //: to `fromEquirectangular`. The equirect path silently produces a black
    //: environment here -- it costs nothing, throws nothing, and leaves every
    //: material lit exactly as if there were no environment at all, which is a
    //: miserable thing to debug by eye. A BackSide sphere with the gradient as a
    //: plain texture is the same picture through a path that demonstrably works.
    const c = document.createElement('canvas');
    c.width = 8;
    c.height = 256;
    const g = c.getContext('2d');
    const grad = g.createLinearGradient(0, 0, 0, 256);
    grad.addColorStop(0.00, '#ffffff');
    grad.addColorStop(0.30, '#d6ecf3');
    grad.addColorStop(0.50, '#7b9fac');
    grad.addColorStop(0.68, '#31454c');
    grad.addColorStop(1.00, '#131c1f');
    g.fillStyle = grad;
    g.fillRect(0, 0, 8, 256);

    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    const probe = new THREE.Scene();
    //: sphere v runs 0 at the bottom pole to 1 at the top, and the texture is
    //: flipped on upload, so the first colour stop lands on the sky. Bright above
    //: and dark below is the whole trick: a curved surface then picks up a
    //: gradient down its length instead of one flat diffuse value.
    probe.add(new THREE.Mesh(
      new THREE.SphereGeometry(60, 24, 32),
      new THREE.MeshBasicMaterial({ map: tex, side: THREE.BackSide })));

    const pmrem = new THREE.PMREMGenerator(renderer);
    const rt = pmrem.fromScene(probe, 0, 0.5, 200);
    pmrem.dispose();
    tex.dispose();
    probe.traverse(o => { if (o.geometry) o.geometry.dispose(); });
    return rt.texture;
  }

  function hexToCol(str) {
    return new THREE.Color().setStyle(String(str), THREE.SRGBColorSpace);
  }

  class MachineScene {
    constructor(el) {
      this.el = el;
      this.caseKey = null;
      this.dynItems = [];
      this.motors = [];
      this.flowItems = [];
      this.flowGroups = [];
      this.root = new THREE.Group();
      //: `_frame` sets this from the built bounding box; until then the group
      //: sits at the origin and `fitDist` is a placeholder the first build
      //: immediately overwrites.
      this.fitDist = 28;
      this.groundY = 0;

      this.scene = new THREE.Scene();
      this.scene.background = new THREE.Color(0x141d20);
      this.scene.add(this.root);

      this.camera = new THREE.PerspectiveCamera(38, 4/3, 0.1, 200);
      this.camDist = 28;
      this.camYaw = 0;
      this.camPitch = 0;
      this._updateCamera();

      this.ambient = new THREE.AmbientLight(0xffffff, 0.46);
      this.scene.add(this.ambient);

      this.hemi = new THREE.HemisphereLight(0x9fd8e4, 0x24343a, 0.5);
      this.scene.add(this.hemi);

      this.keyLight = new THREE.DirectionalLight(0xffffff, 0.95);
      this.keyLight.position.set(-7, 10, 6);
      this.keyLight.castShadow = true;
      this.keyLight.shadow.mapSize.set(1024, 1024);
      this.keyLight.shadow.camera.near = 1;
      this.keyLight.shadow.camera.far = 60;
      this.keyLight.shadow.camera.left = -18;
      this.keyLight.shadow.camera.right = 18;
      this.keyLight.shadow.camera.top = 18;
      this.keyLight.shadow.camera.bottom = -18;
      this.keyLight.shadow.bias = -0.0005;
      this.scene.add(this.keyLight);

      this.fillLight = new THREE.DirectionalLight(0x88ccff, 0.5);
      this.fillLight.position.set(8, 4, -5);
      this.scene.add(this.fillLight);

      this.rimLight = new THREE.DirectionalLight(0xffbb88, 0.4);
      this.rimLight.position.set(2, 6, -8);
      this.scene.add(this.rimLight);

      //: one floor, not two. There used to be a 60x40 opaque ground plane *and*
      //: a 30x14 shadow catcher, both parked at a fixed height that happened to
      //: be above the reservoir -- so the tank was underneath the floor, and
      //: pitching the camera down far enough to see it meant looking through the
      //: floor first. That was the "black blanket". The floor is now a shadow
      //: catcher only: it darkens where the machine occludes the key light and is
      //: otherwise invisible, so it can never hide a part of the machine again.
      this.shadowPlane = new THREE.Mesh(
        new THREE.PlaneGeometry(64, 44),
        new THREE.ShadowMaterial({ opacity: 0.34, transparent: true, depthWrite: false })
      );
      this.shadowPlane.rotation.x = -Math.PI / 2;
      this.shadowPlane.receiveShadow = true;
      this.scene.add(this.shadowPlane);

      const w = el.clientWidth || 400;
      const h = el.clientHeight || 300;
      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      this.renderer.setSize(w, h, false);
      this.renderer.shadowMap.enabled = true;
      this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      this.renderer.outputColorSpace = THREE.SRGBColorSpace;
      this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
      this.renderer.toneMappingExposure = 1.3;
      el.insertBefore(this.renderer.domElement, el.firstChild);

      //: `environment`, not `background`: the panel keeps its flat --panel fill,
      //: and the gradient exists only to be reflected.
      this.env = makeEnvironment(this.renderer);
      this.scene.environment = this.env;

      this._ro = new ResizeObserver(() => this._resize());
      this._ro.observe(el);
    }

    _resize() {
      const w = this.el.clientWidth || 400;
      const h = this.el.clientHeight || 300;
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(w, h, false);
      //: the fit distance is a function of the aspect ratio, so a panel that
      //: reflows (the two views stack on narrow screens) has to re-fit or the
      //: model overflows its own panel.
      if (this.root.children.length) this._frame();
    }

    _updateCamera() {
      const cy = Math.cos(this.camYaw), sy = Math.sin(this.camYaw);
      const cp = Math.cos(this.camPitch), sp = Math.sin(this.camPitch);
      const r = this.camDist;
      this.camera.position.set(r * sy * cp, r * sp, r * cy * cp);
      this.camera.lookAt(0, 0, 0);
    }

    setCamera(yaw, pitch, zoom) {
      this.camYaw = yaw;
      this.camPitch = pitch;
      this.camDist = this.fitDist * (zoom || 1);
      this._updateCamera();
    }

    //: measure what was built, slide it so its centre is the origin, drop the
    //: floor onto its underside, and back the camera off far enough that the
    //: whole box fits the *narrower* of the two frustum angles. Called once per
    //: rebuild, which is the only time the extent can change.
    _frame() {
      this.root.position.set(0, 0, 0);
      this.root.updateMatrixWorld(true);
      const box = new THREE.Box3().setFromObject(this.root);
      if (box.isEmpty()) return;
      const c = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      this.root.position.set(-c.x, -c.y, -c.z);

      this.groundY = box.min.y - c.y - 0.02;
      this.shadowPlane.position.set(0, this.groundY, 0);

      const vFov = (this.camera.fov * Math.PI) / 180;
      const hFov = 2 * Math.atan(Math.tan(vFov / 2) * this.camera.aspect);
      //: half-extent of the box measured across the view, worst case over yaw:
      //: the model is ~20 long and ~8 deep, so a yaw of 90 degrees presents a
      //: very different silhouette than a yaw of 0. Fitting the diagonal keeps
      //: the framing stable while the turntable turns instead of clipping at
      //: one end of the spin and leaving a hole at the other.
      const halfW = 0.5 * Math.hypot(size.x, size.z);
      const halfH = 0.5 * size.y;
      const dW = halfW / Math.tan(hFov / 2);
      const dH = halfH / Math.tan(vFov / 2);
      this.fitDist = Math.max(dW, dH) * FIT_MARGIN;
      this.camera.far = this.fitDist * 4 + 60;
      this.camera.updateProjectionMatrix();

      //: the key light's shadow frustum has to cover the model too, or the
      //: shadow simply stops partway across the floor.
      const rad = 0.5 * Math.max(size.x, size.y, size.z) * 1.5;
      const k = this.keyLight.shadow.camera;
      k.left = -rad; k.right = rad; k.top = rad; k.bottom = -rad;
      k.far = this.fitDist * 3 + 40;
      k.updateProjectionMatrix();
    }

    clearMeshes() {
      const remove = obj => {
        while (obj.children.length) {
          remove(obj.children[0]);
          obj.remove(obj.children[0]);
        }
        if (obj.geometry && obj.geometry.dispose) obj.geometry.dispose();
        if (obj.material) {
          if (Array.isArray(obj.material))
            obj.material.forEach(m => { if (m.dispose) m.dispose(); });
          else if (obj.material.dispose) obj.material.dispose();
        }
      };
      while (this.root.children.length) {
        remove(this.root.children[0]);
        this.root.remove(this.root.children[0]);
      }
      this.dynItems = [];
      this.motors = [];
      this.flowItems = [];
      this.flowGroups = [];
    }

    //: the flow toggle used to be read only inside `addPipe`, i.e. only at build
    //: time -- and the scene rebuilds only when the *case* changes. Unticking the
    //: box therefore did nothing at all until you clicked a different case, which
    //: is exactly how it looked: a dead checkbox. It now flips visibility on
    //: already-built groups, so it takes effect on the next frame.
    setFlowVisible(on) {
      for (const g of this.flowGroups) g.visible = on;
    }

    //: The pipe walls are translucent for one reason: the dots inside them are
    //: the only thing on this page that shows *where the oil goes*, and an opaque
    //: wall hid every one of them. That is why the flow toggle looked dead --
    //: the particles were being built and animated correctly, inside a solid tube.
    //:
    //: `depthWrite: false` on the wall keeps it from occluding the dots behind
    //: it during the transparent pass; the dots themselves stay opaque, so they
    //: are drawn in the opaque pass first and the wall tints over them.
    //: DoubleSide means the far wall of the tube is drawn too, which is what
    //: makes it read as a tube with something inside rather than a coloured strip.
    _makePipeMaterial(color) {
      return new THREE.MeshStandardMaterial({
        color: color, roughness: 0.18, metalness: 0.25, envMapIntensity: 1.4,
        transparent: true, opacity: 0.46, depthWrite: false,
        side: THREE.DoubleSide,
      });
    }
    //: the vessels keep `depthWrite` unlike the pipe walls. Turning it off on a
    //: shape this big leaves its own front and back faces to be ordered by the
    //: renderer's centroid sort, which is not stable frame to frame -- the
    //: reservoir visibly flipped between reading as a pale slab and as a dark
    //: outline depending on what else was in the scene. Chunky solids sort fine
    //: on depth; only the thin tube walls need the dots behind them to survive.
    _makeBoxMaterial(color) {
      return new THREE.MeshStandardMaterial({
        color: color, roughness: 0.32, metalness: 0.2, envMapIntensity: 1.25,
        transparent: true, opacity: 0.72,
        side: THREE.DoubleSide,
      });
    }
    _makeMotorMaterial(color) {
      return new THREE.MeshStandardMaterial({
        color: color, roughness: 0.46, metalness: 0.55, envMapIntensity: 1.15,
      });
    }
    _makeJointMaterial(color) {
      //: joints stay solid. They are where one part meets the next, and this pass
      //: exists partly because those junctions were floating apart -- a translucent
      //: collar would hide the very thing being fixed.
      return new THREE.MeshStandardMaterial({
        color: color, roughness: 0.34, metalness: 0.5, envMapIntensity: 1.2,
      });
    }

    addPipe(pr) {
      const pts3d = pr.pts.map(p => new THREE.Vector3(p[0], p[1], p[2]));
      const mat = this._makePipeMaterial(pr.col);
      this.dynItems.push({ type: 'pipe-color', material: mat, origCol: pr.col });

      //: one curve drives both the wall and the dots inside it. It used to be two
      //: different paths: the wall was a Catmull-Rom spline through the corner
      //: points, the dots walked the straight polyline between them. While the
      //: wall was opaque nobody could tell; the moment it went translucent the
      //: dots visibly cut every bend and left the pipe. A `LineCurve3` for the
      //: straight runs and the same spline for the bent ones means the dots are
      //: parameterised on the geometry they are inside, by construction.
      const path = pts3d.length === 2
        ? new THREE.LineCurve3(pts3d[0], pts3d[1])
        : new THREE.CatmullRomCurve3(pts3d, false, 'catmullrom', 0.4);
      const tubeSeg = pts3d.length === 2 ? 1 : Math.max(28, pts3d.length * 16);
      const tube = new THREE.Mesh(
        new THREE.TubeGeometry(path, tubeSeg, pr.r, 20, false), mat);
      tube.castShadow = true;
      tube.receiveShadow = true;
      this.root.add(tube);

      //: ferrules at the two ends, not beads. Two changes from what was here:
      //:
      //: They used to sit at *every* control point, so a four-point return leg
      //: carried two opaque spheres parked mid-run, chopping the dot stream into
      //: pieces for no reason -- TubeGeometry already rounds its own bends.
      //:
      //: And they used to be spheres, which stopped working the moment the pipe
      //: wall went translucent: a solid ball on a see-through tube reads as a
      //: swelling in the pipe rather than as hardware on it. A short opaque
      //: sleeve squared to the pipe's own tangent reads as a fitting, which is
      //: what the joint actually is. Sleeves at ends that land inside a block or
      //: a motor are simply buried, which is also correct.
      const jointMat = this._makeJointMaterial(pr.col);
      this.dynItems.push({ type: 'joint-color', material: jointMat, origCol: pr.col });
      const ends = [
        { at: pts3d[0], tan: path.getTangentAt(0), sign: 1 },
        { at: pts3d[pts3d.length - 1], tan: path.getTangentAt(1), sign: -1 },
      ];
      for (const e of ends) {
        const dir = e.tan.clone().normalize();
        const sleeve = new THREE.Mesh(
          new THREE.CylinderGeometry(pr.r * 1.24, pr.r * 1.24, pr.r * 1.05, 20, 1, false),
          jointMat);
        sleeve.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
        sleeve.position.copy(e.at).addScaledVector(dir, e.sign * pr.r * 0.5);
        sleeve.castShadow = true;
        sleeve.receiveShadow = true;
        this.root.add(sleeve);
      }

      if (!pr.flow) return;
      const totalL = path.getLength();
      if (!(totalL > 0)) return;

      //: dots stay opaque on purpose. Opaque meshes are drawn before the
      //: transparent pass, so the translucent wall tints over them rather than
      //: hiding them -- that ordering is the whole reason the oil is visible.
      const n = Math.max(FLOW_MIN, Math.round(totalL * FLOW_PER_UNIT));
      const group = new THREE.Group();
      group.visible = FLOW_PARTICLES_ON;
      const pGeo = new THREE.SphereGeometry(
        Math.max(0.07, pr.r * FLOW_DOT_R), 12, 10);
      const pMat = new THREE.MeshStandardMaterial({
        color: 0xd8f2fb, roughness: 0.2, metalness: 0.0,
        emissive: 0x7fd8f0, emissiveIntensity: 0.5,
      });
      const speed = pr.flowSpeed || 0.8;
      for (let i = 0; i < n; i++) {
        const dot = new THREE.Mesh(pGeo, pMat);
        group.add(dot);
        this.flowItems.push({ mesh: dot, path, group, phase0: i / n, speed });
      }
      this.root.add(group);
      this.flowGroups.push(group);
    }

    addBox(b) {
      const [w,h,d] = b.s;
      const geo = new THREE.BoxGeometry(w, h, d, 1, 1, 1);
      const mat = this._makeBoxMaterial(b.col);
      this.dynItems.push({ type: 'box-color', material: mat, origCol: b.col });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(b.c[0], b.c[1], b.c[2]);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      this.root.add(mesh);

      if (b.edge !== false) {
        const edges = new THREE.EdgesGeometry(geo);
        const line = new THREE.LineSegments(edges,
          new THREE.LineBasicMaterial({
            color: hexToCol(shade(b.col, 1.5)),
            transparent: true, opacity: 0.25
          }));
        line.position.copy(mesh.position);
        this.root.add(line);
      }
    }

    addMotor(m) {
      const ax = m.axis === 'x' ? [1,0,0] : [0,1,0];
      const a = [m.c[0]-ax[0]*m.len/2, m.c[1]-ax[1]*m.len/2, m.c[2]];
      const b = [m.c[0]+ax[0]*m.len/2, m.c[1]+ax[1]*m.len/2, m.c[2]];
      const mat = this._makeMotorMaterial(m.col);
      this.dynItems.push({ type: 'motor-color', material: mat, origCol: m.col });

      const geo = new THREE.CylinderGeometry(m.r, m.r, m.len, 28, 1, false);
      const mesh = new THREE.Mesh(geo, mat);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      const mid = [(a[0]+b[0])/2, (a[1]+b[1])/2, (a[2]+b[2])/2];
      mesh.position.set(mid[0], mid[1], mid[2]);
      if (m.axis === 'x') mesh.rotation.z = Math.PI / 2;
      this.root.add(mesh);

      for (const [end, sgn] of [[a, -1], [b, 1]]) {
        const capGeo = new THREE.CircleGeometry(m.r, 28);
        const capMat = this._makeMotorMaterial(shade(m.col, 0.9));
        this.dynItems.push({ type: 'motor-color', material: capMat, origCol: shade(m.col, 0.9) });
        const cap = new THREE.Mesh(capGeo, capMat);
        cap.position.set(end[0], end[1], end[2]);
        if (m.axis === 'x') { cap.rotation.y = -Math.PI/2 * sgn; }
        else { cap.rotation.x = Math.PI/2 * sgn; }
        this.root.add(cap);
      }

      //: The shaft-speed mark: one hand per end face, turning at the motor's own
      //: solved rev/min. This is the only thing in the view that shows a *rate*
      //: rather than a pressure, so it has to be legible.
      //:
      //: It used to be a rod lying along +Y at the end face, spun about Z for an
      //: axis-x motor. An axis-x motor's end faces lie in the YZ plane, so the
      //: hand belongs on a rotation about X; spinning it about Z swept it through
      //: the X direction instead -- straight into the drum. It was inside the
      //: motor body for half of every revolution, and the fix is not to nudge it
      //: outward but to turn it about the axis the shaft actually has.
      //:
      //: Nesting is what keeps that honest. `mount` carries orientation once --
      //: its local +Z is the motor's axis, pointing out of the face it sits on --
      //: and `spin` only ever rotates about its own Z. There is no per-axis
      //: branch left in `animate` to get backwards a second time.
      if (m.w) {
        //: no hub, and the hand starts well off centre: the feed and return lines
        //: pass through both end-face centres, and a boss drawn there would be
        //: buried in a pipe and its ferrule.
        const rIn = m.r * 0.42;
        const rOut = m.r * 0.94;
        const armLen = rOut - rIn;
        const markMat = new THREE.MeshStandardMaterial({
          color: 0x3ddc97, emissive: 0x3ddc97, emissiveIntensity: 0.75,
          roughness: 0.28, metalness: 0.18,
        });

        //: one on each face. The mark is only ever readable on the face turned
        //: towards you, and the camera orbits freely -- with a single hand, half
        //: the angles hide it behind the drum it belongs to.
        //:
        //: The two hands are ends of one rigid shaft, so they have to hold the
        //: same world angle. Their mounts face opposite ways along that shaft --
        //: one mount's local +Z is world +X, the other's is world -X -- and a
        //: positive turn about -X is a negative turn about +X. Turning both by
        //: +theta therefore drove them apart: they scissored open and shut
        //: instead of turning together. `sense` undoes the mount's flip, so both
        //: describe the same rotation of the same shaft.
        for (const [end, sgn] of [[a, -1], [b, 1]]) {
          const mount = new THREE.Group();
          mount.position.set(end[0], end[1], end[2]);
          mount.quaternion.setFromUnitVectors(
            new THREE.Vector3(0, 0, 1),
            new THREE.Vector3(ax[0] * sgn, ax[1] * sgn, ax[2] * sgn));
          mount.translateZ(0.07);

          const spin = new THREE.Group();
          mount.add(spin);

          const arm = new THREE.Mesh(
            new THREE.CylinderGeometry(0.1, 0.1, armLen, 10), markMat);
          arm.position.y = rIn + armLen / 2;
          arm.castShadow = true;
          spin.add(arm);

          const tip = new THREE.Mesh(new THREE.SphereGeometry(0.2, 14, 12), markMat);
          tip.position.y = rOut;
          tip.castShadow = true;
          spin.add(tip);

          this.motors.push({ group: spin, w: m.w, sense: sgn });
          this.root.add(mount);
        }
      }
    }

    build(parts) {
      this.clearMeshes();
      for (const p of parts) {
        if (p.t === 'pipe') this.addPipe(p);
        else if (p.t === 'box') this.addBox(p);
        else this.addMotor(p);
      }
      this._frame();
    }

    updateColors(parts) {
      let idx = 0;
      const applyColor = (dynItem, col) => {
        const c = hexToCol(col);
        if (dynItem.material.color) dynItem.material.color.copy(c);
      };
      for (const p of parts) {
        if (p.t === 'pipe') {
          if (this.dynItems[idx]) applyColor(this.dynItems[idx], p.col); idx++;
          if (this.dynItems[idx] && this.dynItems[idx].type === 'joint-color')
            { applyColor(this.dynItems[idx], p.col); idx++; }
        } else if (p.t === 'box') {
          if (this.dynItems[idx]) applyColor(this.dynItems[idx], p.col); idx++;
        } else if (p.t === 'motor') {
          if (this.dynItems[idx]) applyColor(this.dynItems[idx], p.col); idx++;
          if (this.dynItems[idx] && this.dynItems[idx].type === 'motor-color')
            { applyColor(this.dynItems[idx], shade(p.col, 0.9)); idx++; }
          if (this.dynItems[idx] && this.dynItems[idx].type === 'motor-color')
            { applyColor(this.dynItems[idx], shade(p.col, 0.9)); idx++; }
        }
      }
    }

    animate(tms) {
      for (const motor of this.motors) {
        //: local Z is the shaft axis by construction, whichever way the motor
        //: is oriented in the model.
        motor.group.rotation.z = motor.sense * tms * RPM_SLOW * motor.w / 60;
      }
      const tSec = REDUCED_MOTION ? 0 : (tms * 0.001);
      for (const fl of this.flowItems) {
        if (!fl.group.visible) continue;
        const u = (((tSec * 0.5 * fl.speed + fl.phase0) % 1) + 1) % 1;
        fl.path.getPointAt(u, fl.mesh.position);
      }
    }

    render() {
      this.renderer.render(this.scene, this.camera);
    }

    dispose() {
      this._ro && this._ro.disconnect();
      this.env && this.env.dispose();
      this.clearMeshes();
      this.renderer.dispose();
      if (this.renderer.domElement.parentNode)
        this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
    }
  }

  function getScene(el) {
    const id = el.id || el;
    if (!scenes.has(id)) {
      const s = new MachineScene(el);
      scenes.set(id, s);
    }
    return scenes.get(id);
  }

  function caseSignature(c) {
    if (!c || !c.params || !c.solution) return null;
    const p = c.params;
    return [
      p.displacement, p.p_crack, p.A_relief,
      p.A_valve_a, p.A_valve_b, p.load_torque_a, p.load_torque_b,
      p.w_pump, c.relief_open ? 1 : 0
    ].map(x => (typeof x === 'number' ? x.toFixed(6) : String(x))).join('|');
  }

  function setFlowParticles(on) {
    for (const s of scenes.values()) s.setFlowVisible(on);
  }

  return { getScene, caseSignature, setFlowParticles, MachineScene };
})();

function renderMachine(el, c, tms, label) {
  if (!c || typeof THREE === 'undefined' || !THREE.Scene) return;
  const scene = THREE_D.getScene(el);
  const sig = THREE_D.caseSignature(c);
  const parts = machineParts(c);
  if (scene.caseKey !== sig) {
    scene.build(parts);
    scene.caseKey = sig;
  } else {
    scene.updateColors(parts);
  }
  scene.setCamera(MACH.yaw, MACH.pitch, MACH.zoom);
  scene.animate(tms);
  scene.render();

  const id = el.id;
  const s = c.solution;
  const labelEl = document.getElementById(id + '-label');
  const capEl = document.getElementById(id + '-cap');
  if (labelEl) labelEl.textContent = label;
  if (capEl) capEl.innerHTML =
    `manifold ${Math.round(s.p1)} bar &middot; relief ${c.relief_open ? 'open' : 'closed'}<br>` +
    `shafts ${Math.round(s.w_a)} / ${Math.round(s.w_b)} rev/min`;
}

function stateGap(q, n) {
  return {
    dp: Math.max(
      ...["p1", "p2a", "p3a", "p2b", "p3b"].map((k) =>
        Math.abs(q[k] - n[k]),
      ),
    ),
    dw: Math.max(...["w_a", "w_b"].map((k) => Math.abs(q[k] - n[k]))),
  };
}
function pairGap(P) {
  return stateGap(P.query.solution, P.neighbour.solution);
}
function machDiff(other) {
  return stateGap(subjectPair().query.solution, other.solution);
}

function renderMachPanel() {
  const P = subjectPair();
  const right = MACH.right || P.neighbour;
  const picked = MACH.right && MACH.right.id !== P.neighbour.id;
  const d = machDiff(right),
    best = machDiff(P.neighbour);
  $("#machdiff").innerHTML =
    `<div>largest pressure difference<b>${d.dp.toFixed(1)} bar</b>across five nodes</div>
<div>largest speed difference<b>${Math.round(d.dw)} rev/min</b>across two shafts</div>` +
    (picked
      ? `<div>versus the retrieved case<b>${best.dp.toFixed(1)} bar</b>which is
     ${(d.dp / (best.dp || 1)).toFixed(1)}&times; closer</div>`
      : (() => {
          const R = subjectRace();
          // "solved in — iterations from 10 cold" is not a sentence. When the
          // archive was not used, say that instead of leaving a dash where the
          // result would be.
          return R.warm
            ? `<div>then solved in<b>${R.warm.iterations} iterations</b>from
           ${
             R.cold.converged === false
               ? "a cold start that never converged"
               : R.cold.iterations + " cold"
           }</div>`
            : `<div>then solved in<b style="color:var(--warn)">${
                R.nominal
                  ? R.nominal.iterations + " iterations"
                  : "&mdash;"
              }</b>from the
           nominal guess &mdash; the archive was not used</div>`;
        })());
  //: the point of letting a tile be picked is that picking badly is visible.
  //: A hand-chosen case is a control, and saying how much worse it is turns the
  //: comparison from an illustration into a measurement the room can check.
  $("#machnote").innerHTML = picked
    ? `<b>${esc(MACH.right.id)}</b> picked by hand, not chosen by retrieval &mdash;
 <b>${d.dp.toFixed(1)} bar</b> away against the retrieved case's
 <b>${best.dp.toFixed(1)} bar</b>.`
    : `<b>${esc(P.neighbour.id)}</b> is what retrieval chose out of
 ${VIZ.config.archive_size}.` +
      //: "chose out of 395" is true of `argmin` and of ranked retrieval alike,
      //: and on its own it lets the reader assume the first. When the pick was
      //: not the nearest, saying only that would hide the entire selection step
      //: -- the case on screen would look like the closest one when a closer
      //: one was passed over on purpose.
      (LIVE && LIVE.ranking && !LIVE.ranking.picked_was_nearest
        ? ` Not the nearest: the ${LIVE.ranking.considered} nearest were
      gated, and this one was ranked first among the ${LIVE.ranking.admitted}
      the verifier admitted &mdash; ahead of
      <b>${esc(LIVE.ranking.nearest.case_id)}</b> at
      ${LIVE.ranking.nearest.distance.toFixed(3)}.`
        : "") +
      // the right-hand machine is on screen either way; whether the solver was
      // allowed to start from it is a different fact and belongs beside it
      (LIVE && !LIVE.usedArchive
        ? ` <span style="color:var(--warn)">The verifier refused the transfer, so
      this state was not used as a starting point.</span>`
        : "") +
      ` Click a tile to compare against another.`;
}

function machTick() {
  //: frozen at 0 rather than a live clock reading: `t` drives the shaft-speed
  //: marks in `drawMotor`, the one piece of continuous motion in this view
  //: that isn't gated by the Spin/Stop button. A static mark still shows the
  //: right geometry and colour, just not the turn.
  const t = REDUCED_MOTION ? 0 : performance.now() - MACH.t0;
  if (MACH.spin) MACH.yaw += 0.0022;
  else machCoast();
  //: the two 3D rebuilds are the single most expensive thing this page does
  //: every frame -- ~8ms for both views together -- so this is the loop
  //: `trackVisible` earns its keep on: scrolled past, it costs nothing.
  if (MACH.visible) {
    const P = subjectPair();
    const leftSubject = MACH.overrideState || P.query;
    const leftLabel =
      MACH.overrideLabel || P.query.id + "  (the new run)";
    renderMachine($("#machL"), leftSubject, t, leftLabel);
    renderMachine(
      $("#machR"),
      MACH.right || P.neighbour,
      t,
      (MACH.right || P.neighbour).id + "  (from the archive)",
    );
  }
  MACH.raf = requestAnimationFrame(machTick);
}

/* --- Interactive Newton Convergence Stepper ---------------------------
//: Every state this panel shows is an iterate the solver actually produced.
//:
//: It used to interpolate. With no analysed run it built a start state by hand
//: and eased from there to the answer with `Math.sin(u * PI/2)`, which is not
//: Newton's method and does not look like it: the real cold path on the shipped
//: fixture goes 0 -> 107.9 -> **-20.6** -> 87.9 -> ... -> 134.63 bar, and the
//: drawn one climbed 0 -> 19 -> 38 -> ... -> 134.63 without ever leaving the
//: envelope. That excursion through a negative manifold pressure is the whole
//: reason the admissibility gate exists; smoothing it away made this the one
//: panel on the page whose contents were invented.
//:
//: The iterates were already here. `model.solve(record_path=True)` keeps every
//: one, `POST /api/analyse` returns them as `solve.paths`, and `benchmarks/viz.py` writes
//: them into viz_results.json as `race.<arm>.path_state`. Both are rows in
//: `state_order`, so one reader serves the live run and the fixture.
*/
const STEPPER = {
  arm: "warm",
  step: 0,
  playing: false,
  timer: null,
};

//: the arms that were actually run, in presentation order. A warned-and-not-
//: overridden run never solves a warm arm, so `warm` is genuinely absent from
//: its trace -- and the panel says so rather than manufacturing one.
const STEP_ARMS = ["cold", "nominal", "warm"];
const STEP_ARM_LABEL = {
  cold: "Cold Start",
  nominal: "Nominal Guess",
  warm: "Warm Start",
};

//: the raw iterates for one arm, as states -- or null if that arm was not run.
//: Never interpolated, never defaulted: the only two sources are the pipeline's
//: own `solve.paths` and the fixture's `path_state`.
function armPath(arm) {
  const order = VIZ.projection.transform.state_order;
  const rows = LIVE
    ? (LIVE.paths || {})[arm]
    : (VIZ.race[arm] || {}).path_state;
  if (!rows || !rows.length) return null;
  return rows.map((row) =>
    Object.fromEntries(order.map((n, i) => [n, row[i]])),
  );
}

function getStepperTrajectory() {
  return armPath(STEPPER.arm);
}

//: did that arm actually arrive, or is its last iterate where it gave up? The
//: tab has to say, for the same reason `#geonums` does: "Cold Start (7 iters)"
//: beside "Warm Start (4 iters)" reads as a comparison, and on a case where the
//: flat start stalls it is not one.
function armConverged(arm) {
  return LIVE
    ? (LIVE.converged || {})[arm] !== false
    : (VIZ.race[arm] || {}).converged !== false;
}

//: the tab labels are the measured iteration counts, not text typed into the
//: markup. They used to read "Cold Start (8+ iters)" beside a readout saying
//: "Iteration 0 of 11", because nothing updated them when the subject changed.
function renderStepperArms() {
  const tabs = $("#steparms");
  if (!tabs) return;
  tabs.innerHTML = STEP_ARMS.map((arm) => {
    const p = armPath(arm);
    const on = arm === STEPPER.arm ? " on" : "";
    const note = !p
      ? "not run"
      : !armConverged(arm)
        ? `${p.length - 1} iters, stalled`
        : `${p.length - 1} iters`;
    const why = !p
      ? "this arm was not run for the case on screen"
      : !armConverged(arm)
        ? "this arm never converged -- its last iterate " +
          "is where it gave up, not an answer"
        : "";
    return `<button class="geotab${on}" data-arm="${arm}"${p ? "" : " disabled"}
        aria-pressed="${arm === STEPPER.arm}" title="${esc(why)}"
      >${STEP_ARM_LABEL[arm]} (${note})</button>`;
  }).join("");
}

function updateStepperUI() {
  renderStepperArms();
  const path = getStepperTrajectory();
  const slider = $("#steprange"),
    txt = $("#steptext"),
    readout = $("#stepreadout"),
    playBtn = $("#stepplay");

  //: an arm that was not run has nothing to step through. Every control goes
  //: inert and the readout says which arm and why -- the alternative, and what
  //: this did before, is to invent a path so the slider has something to move
  //: along. The commonest case is a warned transfer the engineer left standing:
  //: the pipeline deliberately never solved a warm arm, and a stepper that
  //: animates one is drawing the transfer the verifier just refused.
  if (!path) {
    STEPPER.playing = false;
    if (STEPPER.timer) {
      clearInterval(STEPPER.timer);
      STEPPER.timer = null;
    }
    MACH.overrideState = null;
    MACH.overrideLabel = null;
    if (slider) {
      slider.disabled = true;
      slider.max = 0;
      slider.value = 0;
    }
    if (playBtn) {
      playBtn.disabled = true;
      playBtn.textContent = "Play";
    }
    if (txt)
      txt.innerHTML = `<span style="color:var(--faint)">no iterates</span>`;
    if (readout) {
      //: only the warm arm can be absent -- the pipeline always solves cold and
      //: nominal -- and it is absent for exactly one reason, so say that reason
      //: rather than leaving an empty panel to be read as a bug.
      const why =
        STEPPER.arm === "warm"
          ? `<div>why<b>the archive was not used</b>the transfer was warned and not overridden</div>`
          : `<div>why<b>this arm is not in the trace</b>nothing to step through</div>`;
      readout.innerHTML =
        `<div>starting guess <b>${esc(STEPPER.arm)} arm</b></div>` +
        `<div>iterates <b style="color:var(--warn)">not run</b>for the case on screen</div>` +
        why;
    }
    return;
  }

  const maxStep = path.length - 1;
  if (STEPPER.step > maxStep) STEPPER.step = maxStep;
  if (slider) {
    slider.disabled = false;
    slider.max = maxStep;
    slider.value = STEPPER.step;
  }
  if (playBtn) playBtn.disabled = false;

  const currState = path[STEPPER.step];
  const P = subjectPair();
  //: the relief valve's state on an *intermediate* iterate, by the same test
  //: `model.regime` applies to a converged one: `relief_opening()` is zero at
  //: and below the cracking pressure and positive above it.
  const p_crack = P.query.params ? P.query.params.p_crack : undefined;

  const isDone = STEPPER.step === maxStep;
  if (isDone && STEPPER.arm === "warm") {
    MACH.overrideState = null;
    MACH.overrideLabel = null;
  } else {
    MACH.overrideState = {
      solution: currState,
      params: P.query.params,
      relief_open: p_crack === undefined ? false : currState.p1 > p_crack,
    };
    MACH.overrideLabel = `${P.query.id} (${STEPPER.arm} start, iter ${STEPPER.step}/${maxStep})`;
  }

  const stepCol = isDone
    ? "var(--ok)"
    : STEPPER.step === 0
      ? "var(--refuse)"
      : "var(--warn)";
  if (txt)
    txt.innerHTML = `Iteration <b style="color:${stepCol}">${STEPPER.step}</b> of ${maxStep}`;

  //: the gap to the converged answer, largest over the five pressure nodes.
  //: A Newton path is not monotone -- on the cold arm this rises before it
  //: falls, and it is allowed to, because that is what the solver did.
  const targetSol = P.query.solution;
  const resProxy = Math.max(
    ...["p1", "p2a", "p3a", "p2b", "p3b"].map((k) =>
      Math.abs(currState[k] - (targetSol[k] || 0)),
    ),
  );

  if (readout) {
    //: Iteration 0 of the warm arm is the single most misread number on this
    //: page. The archived case is drawn right beside it, so the obvious reading
    //: is that step 0 *is* that case -- and it is not: the state was walked
    //: toward this run's parameters before Newton ever saw it, which is the
    //: entire reason the arm is short. Left unsaid, the panel looks like it is
    //: contradicting the one next to it. Said, it is the point.
    const order = LIVE ? LIVE.transfer : "second_order";
    const ORDER_NOTE = {
      second_order:
        "the archived state walked toward this run along the solution " +
        "manifold's tangent <i>and</i> its curvature &mdash; not the archived " +
        "state itself",
      first_order:
        "the archived state walked toward this run along the solution " +
        "manifold's tangent &mdash; not the archived state itself",
      verbatim:
        "the archived state exactly as it was stored &mdash; this card " +
        "carried no tangent to walk along",
    };
    const note =
      STEPPER.step === 0 && STEPPER.arm === "warm" && ORDER_NOTE[order]
        ? `<div>iteration 0 is<b style="font-weight:500;line-height:1.45">${ORDER_NOTE[order]}</b></div>`
        : "";
    readout.innerHTML =
      `<div>starting guess <b>${esc(STEPPER.arm)} arm</b></div>` +
      `<div>manifold pressure <b>${Math.round(currState.p1)} bar</b></div>` +
      `<div>shaft speeds <b>${Math.round(currState.w_a)} / ${Math.round(currState.w_b)} rpm</b></div>` +
      `<div>distance to solved state <b>${resProxy < 1e-3 ? "0.00 (converged)" : resProxy.toFixed(1) + " bar"}</b></div>` +
      note;
  }
}

function stepperBoot() {
  const tabs = $("#steparms");
  if (tabs) {
    // the buttons are rebuilt by renderStepperArms on every update, so the
    // handler lives on the container and reads the arm off the target rather
    // than closing over an element that will not survive the next render
    tabs.onclick = (e) => {
      const b = e.target.closest("button");
      if (!b || b.disabled) return;
      STEPPER.arm = b.dataset.arm;
      STEPPER.step = 0;
      STEPPER.playing = false;
      if (STEPPER.timer) {
        clearInterval(STEPPER.timer);
        STEPPER.timer = null;
      }
      const pb = $("#stepplay");
      if (pb) pb.textContent = "Play";
      updateStepperUI();
    };
  }

  const slider = $("#steprange");
  if (slider) {
    slider.oninput = () => {
      STEPPER.step = parseInt(slider.value, 10);
      STEPPER.playing = false;
      const pb = $("#stepplay");
      if (pb) pb.textContent = "Play";
      updateStepperUI();
    };
  }

  const playBtn = $("#stepplay");
  if (playBtn) {
    playBtn.onclick = () => {
      STEPPER.playing = !STEPPER.playing;
      playBtn.textContent = STEPPER.playing ? "Pause" : "Play";
      if (STEPPER.playing) {
        const path = getStepperTrajectory();
        if (!path) {
          STEPPER.playing = false;
          updateStepperUI();
          return;
        }
        if (STEPPER.step >= path.length - 1) STEPPER.step = 0;
        if (STEPPER.timer) clearInterval(STEPPER.timer);
        STEPPER.timer = setInterval(() => {
          if (!STEPPER.playing) {
            clearInterval(STEPPER.timer);
            return;
          }
          const p = getStepperTrajectory();
          if (p && STEPPER.step < p.length - 1) {
            STEPPER.step++;
            updateStepperUI();
          } else {
            STEPPER.playing = false;
            playBtn.textContent = "Play";
            clearInterval(STEPPER.timer);
          }
        }, 450);
      }
    };
  }

  updateStepperUI();
}

//: Turntable orbit for both panels off one shared camera. Shared is deliberate:
//: the two views exist to be compared, and letting them drift to different
//: angles would make every visual difference between them ambiguous -- is that
//: leg shorter, or just further away? One camera, two subjects.
//:
//: Drag was all this used to do. A model you can only spin about two axes at a
//: fixed distance still reads as a diorama; zoom is what makes it feel like an
//: object you are holding. Wheel and pinch both drive `MACH.zoom`, double-click
//: puts it back.
const MACH_ZOOM_MIN = 0.42,
  MACH_ZOOM_MAX = 2.6;
const MACH_HOME = { yaw: 0.72, pitch: 0.42, zoom: 1 };

function machOrbit() {
  for (const id of ["#machL", "#machR"]) {
    const el = $(id);
    if (!el) continue;
    //: pointer id -> last position, so a second finger is tracked rather than
    //: overwriting the first one's origin and making the model jump.
    const active = new Map();
    let pinch0 = null;

    const stopSpin = () => {
      MACH.spin = false;
      const b = $("#machspin");
      if (b) b.textContent = "Spin";
    };

    el.addEventListener("pointerdown", (e) => {
      el.setPointerCapture(e.pointerId);
      active.set(e.pointerId, [e.clientX, e.clientY]);
      MACH.vyaw = MACH.vpitch = 0;
      stopSpin();
      if (active.size === 2) pinch0 = { d: pinchDist(active), z: MACH.zoom };
      el.classList.add("grabbing");
    });

    el.addEventListener("pointermove", (e) => {
      if (!active.has(e.pointerId)) return;
      const prev = active.get(e.pointerId);
      active.set(e.pointerId, [e.clientX, e.clientY]);

      if (active.size >= 2) {
        //: two fingers is a zoom, not a rotate -- rotating on the average of two
        //: diverging fingers reads as the model fighting you.
        if (pinch0 && pinch0.d > 0) {
          const k = pinchDist(active) / pinch0.d;
          MACH.zoom = clampZoom(pinch0.z / k);
        }
        return;
      }
      const dx = e.clientX - prev[0],
        dy = e.clientY - prev[1];
      //: drag sensitivity scales with zoom: when you are close in, the same
      //: pixel of travel should sweep less of the model, or fine positioning
      //: becomes impossible.
      const k = 0.008 * Math.min(1, MACH.zoom);
      MACH.vyaw = dx * k;
      MACH.vpitch = dy * k;
      MACH.yaw += MACH.vyaw;
      MACH.pitch = clampPitch(MACH.pitch + MACH.vpitch);
    });

    const release = (e) => {
      active.delete(e.pointerId);
      if (active.size < 2) pinch0 = null;
      if (active.size === 0) el.classList.remove("grabbing");
    };
    el.addEventListener("pointerup", release);
    el.addEventListener("pointercancel", release);

    el.addEventListener(
      "wheel",
      (e) => {
        //: the panel owns the wheel only while the cursor is over it. Without
        //: preventDefault the page scrolls out from under the model mid-zoom.
        e.preventDefault();
        stopSpin();
        //: exponential, so one notch is the same proportional step whether you
        //: are pushed right in or backed all the way out.
        MACH.zoom = clampZoom(MACH.zoom * Math.exp(e.deltaY * 0.0011));
      },
      { passive: false },
    );

    el.addEventListener("dblclick", () => {
      MACH.yaw = MACH_HOME.yaw;
      MACH.pitch = MACH_HOME.pitch;
      MACH.zoom = MACH_HOME.zoom;
      MACH.vyaw = MACH.vpitch = 0;
    });
  }
}

function pinchDist(active) {
  const [a, b] = [...active.values()];
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}
const clampPitch = (v) => Math.max(-1.35, Math.min(1.35, v));
const clampZoom = (v) => Math.max(MACH_ZOOM_MIN, Math.min(MACH_ZOOM_MAX, v));

//: a flick keeps turning and slows down instead of stopping dead on release.
//: Called once per frame from machTick, and only when nothing else is driving
//: the camera -- `spin` owns it while the turntable is on.
function machCoast() {
  if (MACH.spin || REDUCED_MOTION) {
    MACH.vyaw = MACH.vpitch = 0;
    return;
  }
  if (Math.abs(MACH.vyaw) < 1e-4 && Math.abs(MACH.vpitch) < 1e-4) return;
  MACH.yaw += MACH.vyaw;
  MACH.pitch = clampPitch(MACH.pitch + MACH.vpitch);
  MACH.vyaw *= 0.92;
  MACH.vpitch *= 0.92;
}

function machBoot() {
  //: the markup ships hardcoded "Stop" -- correct when `MACH.spin` starts
  //: true, wrong (spinning implied, not spinning) the one time it does not:
  //: `prefers-reduced-motion` now starts it stopped, and nothing previously
  //: synced the label to that on boot.
  $("#machspin").textContent = MACH.spin ? "Stop" : "Spin";
  $("#machspin").onclick = () => {
    MACH.spin = !MACH.spin;
    $("#machspin").textContent = MACH.spin ? "Stop" : "Spin";
  };
  //: reverting the right-hand machine to the retrieved case has to revert the
  //: tile that put it there too. It used to clear only `MACH.right`, leaving
  //: `GEO.sel` and the tile's `.on` class set -- so the contact sheet and the
  //: 3D cloud kept a case highlighted that neither machine view was showing
  //: any more, and `renderTiles`'s own click handler (the only other place
  //: that clears `GEO.sel`) was never in this call path.
  $("#machpair").onclick = () => {
    MACH.right = null;
    GEO.sel = null;
    document
      .querySelectorAll(".tile")
      .forEach((x) => x.classList.remove("on"));
    renderMachPanel();
    renderView();
  };
  renderMachPanel();
  machOrbit();
  stepperBoot();
  trackVisible("mach", MACH);
  MACH.raf = requestAnimationFrame(machTick);
}

// The header mark blinks on its own clock. CSS cannot express "random", and a
// fixed interval reads as a metronome within about three blinks -- the eye
// stops looking alive and starts looking like a loading spinner. So the delay
// is drawn fresh each time, and the class is removed on `animationend` rather
// than on a second timer that could drift out of step with the CSS duration.
// Paused while the tab is hidden: a timer firing into a backgrounded tab buys
// nothing, and browsers throttle it unevenly anyway.
function blinkLoop() {
  const mark = $("#mark");
  if (!mark) return;
  // The gradient flows via SMIL, which no media query can reach -- CSS can only
  // switch off the blink. So reduced motion is honoured here, by stopping the
  // SVG's own animation clock, and then leaving before the blink is scheduled.
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    mark.pauseAnimations?.();
    return;
  }

  const delay = () => 2000 + Math.random() * 3000; // 2-5 s
  let timer = null;

  mark.addEventListener("animationend", () => mark.classList.remove("blink"));

  const tick = () => {
    if (!document.hidden) {
      // Clear-reflow-set rather than a bare `add`. Re-adding a class that is
      // already present does not restart a CSS animation, so if `animationend`
      // is ever missed -- it does not fire at all while the document is not
      // compositing -- the class would stick and the eye would blink once and
      // then never again. Forcing the reflow makes each tick re-trigger on its
      // own terms instead of depending on the previous one having cleaned up.
      mark.classList.remove("blink");
      void mark.offsetWidth;
      mark.classList.add("blink");
    }
    timer = setTimeout(tick, delay());
  };
  timer = setTimeout(tick, delay());

  document.addEventListener("visibilitychange", () => {
    clearTimeout(timer);
    if (!document.hidden) timer = setTimeout(tick, delay());
  });
}

async function boot() {
  blinkLoop();
  try {
    renderHealth(await (await fetch("/api/health")).json());

    $("#backend").onchange = explain;
    // focus fires before the popup opens, so the next open is already correct
    $("#backend").addEventListener("focus", refreshHealth);
    // coming back to the tab after fixing something outside the browser
    window.addEventListener("focus", refreshHealth);
    // and a slow backstop for the case where neither of those happens
    setInterval(refreshHealth, 15000);

    // A view is not allowed to take the pipeline down with it. A fresh
    // clone that has not run the reproducer says so here rather than throwing.
    // `#flow` exists (hidden) whether or not viz loads below, so it is tracked
    // here rather than inside geoBoot/machBoot.
    trackVisible("flow", FLOW);
    flowTick();

    geoBoot().catch(() => {
      $("#geo").innerHTML =
        '<div class="geomissing">geometry unavailable &mdash; run ' +
        "<code>python run_all.py</code> to generate viz_results.json</div>";
      $("#mach").remove(); // it reads the same file; do not leave two empty frames
      // `#stepper` reads it too, more directly than `#mach` does:
      // `armPath()` dereferences `VIZ.projection.transform.state_order`
      // unconditionally, live case or fixture. `machBoot()` -- the only
      // place that wires up its tabs, slider and Play button -- is the last
      // line of a successful `geoBoot()`, so on this path none of that ever
      // ran: the tabs, slider and Play button all render with no listener on
      // any of them, a fully interactive-looking widget that is entirely
      // dead, and nothing on screen said why.
      $("#stepper").remove();
    });

    SAMPLES = await (await fetch("/api/samples")).json();
    $("#samples").innerHTML = SAMPLES.map(
      (s, i) =>
        `<button class="chip" data-i="${i}">${esc(s.name)}</button>`,
    ).join("");
    $("#samples").onclick = (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      document
        .querySelectorAll(".chip")
        .forEach((c) => c.classList.remove("on"));
      b.classList.add("on");
      $("#text").value = SAMPLES[+b.dataset.i].text;
      $("#text").dataset.name = SAMPLES[+b.dataset.i].name;
      // a stale "loaded x.log" confirmation from a previous drop/browse would
      // otherwise keep describing a file that is no longer what's in the box
      $("#loadhint").textContent = "";
    };
    if (SAMPLES.length) document.querySelector(".chip").click();
  } catch (e) {
    $("#out").innerHTML =
      `<div class="err">cannot reach the API: ${esc(e.message)}</div>`;
  }
}

// drag a file straight onto the textarea
const ta = $("#text");
ta.addEventListener("dragover", (e) => {
  e.preventDefault();
  ta.style.borderColor = "var(--teal)";
});
ta.addEventListener("dragleave", () => (ta.style.borderColor = ""));
//: one loader for both ways in. Dropping a file always worked; nothing on
//: screen said so, and an affordance nobody can see is not one — hence the
//: button beside Analyse, which opens the same picker and lands in the same
//: place. Reading happens in the browser: the file's text is posted like any
//: pasted artifact, so there is no upload endpoint and nothing touches disk.
function loadFile(f) {
  if (!f) return;
  const r = new FileReader();
  r.onload = () => {
    ta.value = r.result;
    ta.dataset.name = f.name;
    document
      .querySelectorAll(".chip")
      .forEach((c) => c.classList.remove("on"));
    $("#loadhint").textContent =
      `loaded ${f.name} (${(f.size / 1024).toFixed(1)} kB)`;
  };
  r.onerror = () => {
    $("#out").innerHTML =
      `<div class="err">could not read ${esc(f.name)}</div>`;
  };
  r.readAsText(f);
}

ta.addEventListener("drop", (e) => {
  e.preventDefault();
  ta.style.borderColor = "";
  loadFile(e.dataTransfer.files[0]);
});

$("#loadfile").onclick = () => $("#fileinput").click();
$("#fileinput").onchange = (e) => {
  loadFile(e.target.files[0]);
  e.target.value = "";
};

//: the request that produced what is on screen. An override has to re-analyse
//: *the same artifact*, not whatever the textarea happens to hold by then.
let LAST_REQ = null;

async function analyse(req) {
  const btn = $("#run");
  btn.disabled = true;
  btn.textContent = "Analysing…";
  try {
    const res = await fetch("/api/analyse", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(req),
    });
    if (!res.ok) {
      // FastAPI's 422 detail is an array of objects, not a string — rendering it
      // straight gives the user "[object Object]", which says nothing about
      // what went wrong. Flatten anything that is not already text.
      const d = (await res.json().catch(() => ({}))).detail;
      const detail = !d
        ? res.statusText
        : typeof d === "string"
          ? d
          : (Array.isArray(d) ? d : [d])
              .map((x) =>
                x && x.msg
                  ? `${(x.loc || []).slice(1).join(".")}: ${x.msg}`
                  : JSON.stringify(x),
              )
              .join("; ");
      $("#out").innerHTML =
        `<div class="err">HTTP ${res.status} &mdash; ${esc(detail)}</div>`;
    } else {
      LAST_REQ = req;
      const trace = await res.json();
      draw(trace);
      // the geometry below is about this run now, not about the shipped fixture
      try {
        adoptFlow(trace);
      } catch (e) {
        /* a view must never break the pipeline */
      }
      try {
        if (VIZ) adoptTrace(trace);
      } catch (e) {
        /* a view must never break the pipeline */
      }
    }
  } catch (e) {
    $("#out").innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
  btn.disabled = false;
  btn.textContent = "Analyse";
}

$("#run").onclick = () =>
  analyse({
    text: ta.value,
    name: ta.dataset.name || "pasted-artifact.log",
    backend: $("#backend").value,
  });

//: The report the engineers asked for: what happened, what it means, and --
//: when the verdict is a warning rather than a fact -- the control that lets
//: them take the risk themselves. A block never renders one.
function reportBlock(r) {
  if (!r) return "";
  const cls =
    r.severity === "ok"
      ? "ok"
      : r.severity === "warn"
        ? "warned"
        : "blocked";
  const head =
    r.severity === "ok"
      ? "report"
      : r.severity === "warn"
        ? "warning &mdash; the decision is yours"
        : "blocked &mdash; nothing here for you to decide";
  let html = `<div class="report ${cls}">
<div class="rhead">${head}${r.override_applied ? " &middot; override applied" : ""}</div>
<div class="rreason">${esc(r.reason)}</div>
<div class="rcons">${esc(r.consequence)}.</div>`;
  if (r.override_available) {
    const who = localStorage.getItem("ds.operator") || "";
    html += `<div class="ovr">
<div class="ovrhint">Accepting this warning is recorded against your name.</div>
<input id="op" placeholder="your name" value="${esc(who)}">
<input id="basis" placeholder="why you are accepting it">
<button id="override-go" class="ovrbtn">Warm-start anyway</button>
</div>`;
  }
  return html + "</div>";
}

function auditBlock(t) {
  if (!t.audit || !t.audit.length) return "";
  return (
    `<div class="audit"><div class="ahead">audit trail</div>` +
    t.audit
      .map(
        (a) =>
          `<div class="arow"><span class="at">${esc(a.at)}</span> ` +
          `${esc(a.action)} by <b>${esc(a.operator || "unattributed")}</b> ` +
          `[${esc(a.rule || "-")}] &mdash; ${esc(a.basis || "no basis stated")}</div>`,
      )
      .join("") +
    `</div>`
  );
}

function draw(t) {
  let html = "";

  // headline: the number, when there is one.
  //
  // Gated on the warm arm having *run*, not on the cold-vs-warm agreement being
  // computable. Requiring `agreement` meant the metric block disappeared
  // entirely whenever the flat start failed -- which is to say, on precisely the
  // cases where the warm start does the most good. Those runs fell through to
  // the verdict bar and read "warm_started - cold start, 7 iterations".
  const s = t.solve;
  if (s && s.warm_iterations !== undefined) {
    //: a baseline that did not converge shows why instead of its iteration
    //: count. The count is real, but it is where that arm gave up, and setting
    //: it in the same large numeral beside a converged one invites the room to
    //: read it as a finish line.
    const arm = (key, cls, label) => {
      const n = s[`${key}_iterations`],
        ok = s[`${key}_converged`];
      if (n === undefined) return "";
      return (
        `<div class="metric"><div class="k">${label}</div>` +
        (ok === false
          ? `<div class="v" style="color:var(--refuse);font-size:14px"
         title="${esc(s[`${key}_status`] || "")}">did not converge</div>`
          : `<div class="v ${cls}">${n}</div>`) +
        `</div>`
      );
    };
    //: the nominal guess sits between the two on purpose: it is the baseline
    //: the warm start actually has to beat, not the flat start
    const agree =
      s.agreement !== undefined
        ? `<div class="v same">same answer as ${esc(s.agreement_against || "baseline")}
     to ${s.agreement.toExponential(1)}</div>`
        : // no converged baseline means no second opinion, and the panel says so
          // rather than leaving a gap that reads as agreement
          `<div class="v same" style="color:var(--warn)">no converged baseline</div>`;
    html += `<div class="headline">
${arm("cold", "cold", "cold start")}
${arm("nominal", "nominal", "nominal guess")}
<div class="arrow">&rarr;</div>
${arm("warm", "warm", "warm start")}
<div class="metric"><div class="k">Newton iterations</div>
  ${agree}</div>
</div>`;
  } else {
    const sev = (t.report || {}).severity;
    const cls = t.outcome.startsWith("warm_started")
      ? "ok"
      : sev === "warn"
        ? "warned"
        : "blocked";
    html += `<div class="verdictbar ${cls}">${esc(t.outcome)} &mdash; ${esc(t.summary || "")}</div>`;
  }

  html += reportBlock(t.report);

  // the pipeline stages
  html += '<div id="stages">';
  t.stages.forEach((st, i) => {
    const glyph =
      { ok: "&check;", warned: "!", blocked: "&times;" }[st.state] ||
      "&middot;";
    let extra = "";
    const sug = st.detail && st.detail.suggestion;
    if (sug) {
      const vals = Object.entries(sug.values)
        .map(([k, v]) => `${esc(k)} = <b>${fmt(v)}</b>`)
        .join(", ");
      extra += `<div class="sugg">nearest on the ${esc(sug.on_fields)} parameters it did read:
          ${esc(sug.case_id)} (${sug.distance.toFixed(2)} away) &mdash; ${vals}</div>`;
    }
    if (st.detail && st.detail.note)
      extra += `<div class="note">${esc(st.detail.note)}</div>`;
    if (st.detail && st.detail.overridden && st.detail.basis)
      extra += `<div class="sugg">basis: ${esc(st.detail.basis)}</div>`;
    // Context, deliberately not a verdict. Proximity to a failed run predicts
    // whether a *case* is hard (AUC 0.77) and barely predicts whether a
    // *transfer* is legitimate (0.63), so it is stated as two distances and
    // nothing is concluded from it on screen.
    // What Layer 1 read out of an artifact from another domain. Shown because
    // the refusal is only convincing if you can see that the file *was* read:
    // "I could not parse your file" and "this is a 3D structural deck, 6 nodes,
    // linear static, and none of its fields exist in this schema" are different
    // sentences, and only one of them tells an engineer what to do next.
    const fg = st.detail && st.detail.foreign;
    if (fg) {
      extra +=
        '<div class="foreign">' +
        Object.entries(fg)
          .map(
            ([k, val]) =>
              `<div><span class="fk">${esc(k)}</span>${esc(val)}</div>`,
          )
          .join("") +
        "</div>";
    }
    const nf = st.detail && st.detail.nearest_failure;
    if (nf) {
      extra +=
        `<div class="sugg">indexed on <b>${esc(st.detail.indexed_on)}</b> parameters &middot; ` +
        `nearest of ${nf.archive_failures} failed runs: ${esc(nf.case_id)} ` +
        `(${nf.distance.toFixed(2)} away, ${esc(nf.status)})</div>`;
    }
    html += `<div class="stage ${st.state}" style="animation-delay:${i * 90}ms">
 <div class="dot">${glyph}</div>
 <div><div class="name">${esc(st.title)}</div><div class="sub">${esc(st.subtitle)}</div></div>
 <div><div class="msg">${esc(st.headline)}</div>${extra}</div>
</div>`;
  });
  html += "</div>";

  // the Case Card
  html += `<table><thead><tr><th>parameter</th><th style="text-align:right">value</th>
     <th>unit</th><th>read from</th></tr></thead><tbody>`;
  t.fields.forEach((f) => {
    html +=
      f.value === null || f.value === undefined
        ? `<tr><td>${esc(f.name)}</td><td class="miss" colspan="3">NOT READ FROM ARTIFACT</td></tr>`
        : `<tr><td>${esc(f.name)}</td><td class="num">${fmt(f.value)}</td>
     <td class="unit">${esc(f.unit)}</td><td class="raw">${esc(f.raw || "")}</td></tr>`;
  });
  html += "</tbody></table>";

  //: hardware overrides this specific artifact stated. Almost always empty --
  //: these 18 fields are optional, and most cases state none of them -- so
  //: nothing renders when it is. When it is not empty, it has to render:
  //: these values change the solve (they feed `model.hardware(p)` the same
  //: way the seven fields above do), and a value that moves the answer while
  //: leaving no trace on the Case Card the operator is looking at is exactly
  //: the silent wrongness this page's whole argument is built to refuse.
  if (t.hardware_overrides && t.hardware_overrides.length) {
    html += `<div class="sugg" style="padding:10px 16px 4px">
<b>hardware stated, not part of the 7-parameter sweep</b> --
overrides the model default and is used in the solve below:</div>`;
    html += `<table><thead><tr><th>constant</th><th style="text-align:right">value</th>
       <th>unit</th><th>default</th><th>read from</th></tr></thead><tbody>`;
    t.hardware_overrides.forEach((f) => {
      html += `<tr><td>${esc(f.name)}</td><td class="num">${fmt(f.value)}</td>
         <td class="unit">${esc(f.unit)}</td>
         <td class="unit">${fmt(f.default)}</td>
         <td class="raw">${esc(f.raw || "")}</td></tr>`;
    });
    html += "</tbody></table>";
  }

  // converged state
  if (t.solution) {
    html += `<table><thead><tr><th>converged state</th>
       <th style="text-align:right">value</th><th>unit</th></tr></thead><tbody>`;
    t.solution.forEach((x) => {
      html += `<tr><td>${esc(x.name)}</td><td class="num">${x.value.toFixed(2)}</td>
         <td class="unit">${esc(x.unit)}</td></tr>`;
    });
    html += "</tbody></table>";
  }

  html += auditBlock(t);

  $("#out").innerHTML = html;

  // wired after the markup lands, so the handler always points at the report
  // currently on screen rather than a stale one
  const go = $("#override-go");
  if (go)
    go.onclick = () => {
      const operator = ($("#op").value || "").trim() || "unattributed";
      const basis = ($("#basis").value || "").trim();
      localStorage.setItem("ds.operator", operator);
      analyse(
        Object.assign({}, LAST_REQ, { override: true, operator, basis }),
      );
    };
}

boot();
