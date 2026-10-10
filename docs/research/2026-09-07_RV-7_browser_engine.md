# RV-7: Browser technology for a hex-and-counter wargame

Research date: 2026-09-07. Every version, number, and license in this document comes from a page that the research agent fetched on that date. The References section lists each page. Where a page did not show a fact, the text says so.

Scope: a deterministic rules engine, hot-seat and LAN play, and replay. A Python reinforcement-learning (RL) trainer must run the same rules engine at tens of thousands of environment steps/s or more.

## Summary of the recommendation

Option 1(b) is the recommendation: one Rust crate for the rules engine, with two thin binding crates. One binding crate uses wasm-bindgen for the browser. The other uses PyO3 and maturin for the Python trainer. The evidence for this decision is in section 1.5.

## 1. Engine-sharing architecture

### 1.1 Option (a): TypeScript engine in the browser and in Node.js, with a Python bridge

Node.js runs compute-bound code much faster than CPython. The Benchmarks Game page for Python 3.13.0 against Node.js v23.8.0 shows these fastest-program times [R1]:

| Benchmark | Python 3 (s) | Node.js (s) |
|---|---|---|
| fannkuch-redux | 943.88 | 11.07 |
| n-body | 372.41 | 8.55 |
| spectral-norm | 349.68 | 1.60 |
| mandelbrot | 182.94 | 4.05 |
| binary-trees | 33.37 | 8.61 |
| pidigits | 1.15 | 1.15 |

The agent found no published throughput numbers for a Node.js board-game rules engine in RL training. This is a gap in the evidence, not a negative result.

The bridge is the weak point of option (a). Each environment step must go across a process boundary. The gRPC performance guide says that in Python, "streaming RPCs create extra threads for receiving and possibly sending the messages" and that streaming RPCs are slower than unary RPCs in Python [R2]. The guide recommends asyncio for Python and says to keep and use the same channels and stubs [R2]. Current bridge library versions from the registries [R3, R4]:

- @grpc/grpc-js 1.14.4 (npm, 2026-05-20, Apache-2.0)
- zeromq 6.7.0 (npm, 2026-09-04, MIT AND MPL-2.0)
- grpcio 1.83.1 (PyPI, 2026-08-28)
- pyzmq 27.2.0 (PyPI, 2026-08-20)

A bridge must batch many environments into one message for each step to get near the target throughput. The agent found no fetched page with a measured steps-per-second figure for such a bridge.

### 1.2 Option (b): Rust engine to WebAssembly and to a Python extension

Tooling versions as seen on 2026-09-07 [R4, R5]:

- pyo3 crate 0.29.2 (crates.io, updated 2026-08-28)
- wasm-bindgen crate 0.2.128 (crates.io, updated 2026-09-04)
- maturin 1.15.0 (PyPI, 2026-08-24)
- wasm-pack: repository moved to the wasm-bindgen organization, dual licensed Apache-2.0 and MIT, 7.3k stars [R6]

One crate, two binding layers. In PyO3 discussion #1935, maintainer davidhewitt answered on 2021-10-20. The maintainer knew of no package that makes bindings for Wasm and Python in one framework. The same maintainer wrote: "You could use `#[wasm_bindgen]` to create Wasm bindings, but there will be some duplication." The person who put the question reported success on 2021-11-03 with Cargo features and `#[cfg(feature = "pybindings")]` on the PyO3 code, and `wasm-pack build -- --features jsbindings` for the browser build [R7].

Real projects that ship the two targets from one Rust core:

- Automerge. The README says the project has a Rust core, a JavaScript package built on `automerge-wasm` with wasm-bindgen, and C FFI bindings. License MIT [R8]. A second repository, `automerge-py`, builds Python bindings with maturin and PyO3. License MIT. The page shows 121 commits and recent updates [R9].
- Ruff. The `pyproject.toml` on branch `main` uses maturin (version 1.9.3 minimum, below 2.0) as the build backend, version 0.16.6, license MIT [R10]. The `ruff_wasm` crate builds three npm packages with wasm-bindgen and has the same version 0.16.6 [R11].
- y-crdt. The `ypy` repository wrapped the Rust `yrs` crate with PyO3. GitHub archived it on 2025-04-22 and points users to `pycrdt` [R12].

Speed evidence for the Rust path:

- rlox (Rust RL data plane with PyO3, dual licensed MIT or Apache-2.0) reports "2.7M steps/s at 512 envs" for parallel environment stepping and "3.1x vs SB3" for an end-to-end rollout. The benchmark date on the page is 2026-04-08, on an Apple M3 Pro, CPU only [R13].
- WebAssembly against native code: Jangda and others (2019) measured SPEC CPU programs and found "applications compiled to WebAssembly run slower by an average of 45% (Firefox) to 55% (Chrome)", with peak slowdowns of 2.08x in Firefox and 2.5x in Chrome [R14].

Pyodide path for Rust extensions. Simon Willison (2026-02-06) documents a build of PyO3 and maturin extension modules as WebAssembly wheels for Pyodide 0.28 and higher. The build must have maturin 1.0 or a higher version and an Emscripten SDK that matches the Pyodide version. It also must have a Rust nightly toolchain with the flag `-Z emscripten-wasm-eh` [R15]. This path is only necessary if the browser must run Python. The recommended architecture does not use it.

### 1.3 Option (c): Python engine as the single source of truth

Server frameworks, versions as seen [R3, R16, R17]:

- FastAPI 0.141.1 (PyPI, 2026-07-29). The WebSocket page says FastAPI uses the `websockets` library and re-exports `WebSocket` from Starlette. The page warns that in-memory connection management "only works with a single process" [R16].
- websockets 17.1 (PyPI, 2026-08-26). uvicorn 0.52.4 (PyPI, 2026-08-19).
- Django Channels 4.3.2 (PyPI, 2025-11-20, BSD). The documentation describes Daphne as "the HTTP and Websocket termination server" and describes channel layers with an optional Redis backend [R17].

The agent found no fetched page with a measured LAN round-trip latency for a FastAPI or Channels turn-based game server. For a turn-based game on a LAN, this gap is not important. A move is one small message. The rules engine, not the socket, sets the time for each move.

The RL problem with option (c) is CPU speed. The Benchmarks Game numbers above show CPython 10x to 200x slower than Node.js on compute-bound tests [R1]. A Spheron article (2026-06-09) gives "Typical: 80,000-150,000 steps/sec for CartPole with 512 envs" on CPU [R18]. CartPole is a trivial environment. A hex wargame rules engine does far more work for each step.

EnvPool shows what a C++ engine gives: 49,439 Atari frames/s on a 12-core laptop and 1,069,922 on 256 cores, and the page says "3.1x / 2.9x" of the gym baseline on 12 cores. EnvPool is Apache 2.0 and supports Python 3.12 to 3.14 [R19].

Pyodide as the in-browser alternative. LWN (2021-05-11) gives this quotation from the Pyodide 0.17 release: "Performance ranges between near native to up to 3 to 5 times slower, depending on the benchmark." The same article quotes the 2019 figure of "around 1x-12x slower than native on Firefox and 1x-16x slower on Chrome" [R20]. The Pyodide FAQ on branch `main` says "fork and pthreads do not work in Pyodide" and that a thread start raises a RuntimeError [R21]. The Pyodide npm package is 314.0.6 (2026-08-25, MPL-2.0) [R3].

The agent found no newer official Pyodide benchmark page that it could fetch. The Pyodide blog and docs gave HTTP 403.

### 1.4 Option (d): C or Zig engine with WASM and ctypes or cffi

Tooling versions as seen:

- Emscripten 6.0.9, dated 09/01/26 in the changelog [R22].
- Zig 0.16.0, released 2026-04-13 [R23]. Zig is not at version 1.0.
- cffi 2.1.1 (PyPI, 2026-08-03) [R3]. The cffi overview says API mode "can be massively faster (and works better than libffi ever will)" than ABI mode [R24].
- ctypes is in the Python 3.14.7 standard library. The docs title is "A foreign function library for Python". It loads shared libraries and runs their functions [R25].

Evidence that C engines reach RL throughput. PufferLib documentation says "Ocean environments are written in C." The site claims "20,000,000 step/second training in only ~5k lines of CUDA" and a Pong demo "Running at 1M+ steps per second directly in your browser" [R26, R27]. PufferLib is MIT [R28]. The PyPI release is 3.0.0 (2025-06-23) and the docs reference version 4.0 [R3, R27].

Evidence that one C or C++ code base ships to WASM. box2d-wasm compiles Box2D v2.4 with Emscripten to WebAssembly, with TypeScript types generated from WebIDL. License Zlib [R29].

Zig to WASM: the `wasm32-freestanding` target and the `export` keyword give a WASM module with exported functions. The agent did not fetch a page that shows a Zig project with a WASM build and also a Python binding.

### 1.5 Decision

The sources favor alternative (b) for this developer.

1. RL throughput. In-process Rust stepping through PyO3 gets to millions of steps/s on one laptop [R13]. A pure-Python engine starts from a 10x to 200x CPU deficit against Node.js alone [R1]. Option (a) adds a process boundary that no fetched page measured for this use.
2. One source of truth. Automerge and Ruff show that one Rust crate can ship a wasm-bindgen package and a maturin package at the same version [R8, R9, R10, R11]. The PyO3 maintainers describe the Cargo-feature pattern that makes this work [R7].
3. Python stays the trainer language. PyO3 makes the engine a standard Python extension module. The sibling projects keep their Python tooling.
4. Browser speed is sufficient. WebAssembly runs at 45% to 55% mean slowdown against native [R14]. That is much faster than an interpreted engine, and a turn-based game must do only one move evaluation at a time.

Option (d) is the fallback if the developer will not use Rust. PufferLib proves the throughput of C environments [R26, R27]. The cost is manual memory management, hand-written cffi and Emscripten code, and no typed bindings like wasm-bindgen gives. Zig 0.16.0 is pre-1.0 [R23] and has no fetched dual-target example.

Option (c) is sufficient for LAN play alone. It cannot give the RL throughput unless the engine moves out of pure Python, which turns it into option (b) or (d).

Option (a) is possible if the developer prefers TypeScript. It must have a batched bridge, and the trainer must then have a Node.js process. The developer must measure the bridge, because no fetched page gives a number.

## 2. Rendering

Board dimensions: 4 boards of 33 x 10 hexes is 1,320 hexes, plus some hundreds of counters. This is small. Wikipedia describes the first 1977 boards as "10 columns of hexes high by 32 hexes wide" [R30]. The project spec says 33 wide. Confirm the count before you write the map generator.

### 2.1 Guidance from fetched sources

- Apache ECharts handbook: "For larger amounts of data (>1k is an experience value), canvas renderer is always recommended." SVG "has less memory usage (which is important for mobile devices)" and stays sharp when you zoom in [R31].
- JointJS (2025-08-23): "SVG is actually more performant with a small number of objects, or over a large surface area." With a small surface area or many objects, the page puts Canvas in front. SVG elements get pointer input from the DOM, and end-to-end test tools can find them. Canvas must have custom hit testing [R32].
- MDN canvas optimization [R33]. The tips are:
  - Pre-render content that you paint many times to an offscreen canvas.
  - Use integer coordinates.
  - Do not scale in `drawImage()`.
  - Use layered canvases.
  - Use CSS transforms to scale.
  - Set `alpha: false` when possible.
  - Do not use `shadowBlur`.
  - Use `requestAnimationFrame()`.
- Shirajuki benchmark (10,000 moving sprites, Edge 109, Ryzen 5 4500U): Kontra 60 FPS, Babylon.js 56, Pixi.js 47, Phaser 43, Kaboom/Kaplay 3 [R34]. The page does not show a benchmark date.

### 2.2 Libraries and versions

- PixiJS 8.20.1 (npm, 2026-08-26, MIT) [R3].
  - The v8 launch post (2024-03-05) reports bunnymark numbers for 100k sprites: v7 CPU ~50 ms against v8 CPU ~15 ms when all move, and ~21 ms against ~0.12 ms when none move. v8 has WebGPU and WebGL renderers [R35].
  - Release 8.16.0 (2026-02-04) added an "early, experimental" Canvas 2D renderer. It "handles core use cases: sprites, graphics, text, and basic filters". It is the automatic fallback when no GPU context is available [R36].
  - The event-system page documents `eventMode`, `hitArea`, and `interactiveChildren`. It says a custom `hitArea` decreases the objects that hit testing must examine [R37].
  - The performance guide says sprites batch "with up to 16 different textures (dependent on hardware)", culling is off by default, and bitmap text is faster for text that changes [R38].
- Phaser 4. Wikipedia: Phaser 4 released 2026-04-10, v4.1.0 on 2026-04-30, MIT, with "both a canvas and WebGL renderer" [R39]. npm shows 4.2.1 (2026-07-09, MIT) [R3]. Release Candidate 4 (2025-05-23) reports filter and mask buffer speed increases "of up to 16x on mobile devices" [R40].
- OffscreenCanvas. MDN marks it "Widely available" since March 2023. It supports `2d`, `webgl`, and `bitmaprenderer` contexts, `transferControlToOffscreen()`, and `requestAnimationFrame()` in a worker [R41].

### 2.3 Recommendation for rendering

Use one Canvas 2D layer stack or PixiJS with the WebGL renderer. The hex count is below the ECharts 1k threshold, but counters, hover highlights, and pan and zoom favor Canvas or WebGL more than SVG DOM nodes. Keep the map as one pre-rendered texture for each board. Show counters as sprites from a generated atlas. Do hit testing in hex math, not in the DOM. Move the render loop to a worker with OffscreenCanvas only if a profile shows main-thread stalls.

## 3. Hex grid math and libraries

- Red Blob Games hex page. Last modified 2026-07-24. Covers offset, cube, axial, and doubled coordinates, distance, line drawing, range, field of view, rotation, rings, and pathfinding [R42]. The implementation page (modified 2026-07-26) generates code in C++, Python, C#, Haxe, Java, JavaScript, TypeScript, and Lua, with distance, line, neighbor, and rotation functions. The page does not give a license for the code [R43].
- Honeycomb (`honeycomb-grid`) 4.1.5 (npm, 2023-11-20, MIT) [R3]. The README says the authors wrote it in TypeScript for browsers and Node 16 or higher. It has traversers for rectangle, ring, line, and spiral shapes, an A* example, and line-of-sight and field-of-view functionality. 704 stars, 8 open issues [R44]. The last npm publish was on 2023-11-20, almost three years before this report.
- Hex LOS in JavaScript. The agent found no maintained JavaScript library with a dedicated hex LOS function other than Honeycomb. Sources for the algorithm: zvold (2010-02-07) gives pseudocode that finds each hexagon that a line goes across [R45]. The Swift library `fananek/hex-grid` (MIT) has a shadow-casting field of view for hex grids and a get-line function, and is a reference for a port [R46]. `euoia/hex-grid.js` (ISC) has pathfinding and neighbors but no LOS [R47].

Recommendation: implement hex math in the Rust engine crate from the Red Blob pseudocode. The LOS rule set of a 1977 Squad Leader-style game (hex center to hex center, blocked by terrain depictions) belongs to this game. A library will not agree with it.

## 4. Turn and phase management, multiplayer

### 4.1 boardgame.io

- npm 0.50.2, published 2022-11-10, MIT [R3].
- GitHub: MIT, 12.4k stars [R48]. The five most recent commits (2026-08-02 to 2026-08-10) are dependency bumps, a Dependabot grouping change, and an ESLint config migration [R49]. No feature release since 0.50.2.
- Changelog [R50]:
  - Phases since v0.16.0.
  - Stages since v0.33.0 with `endStage` and `setStage`.
  - MCTS bot since v0.23.0.
  - Lobby since v0.23.0 with expansion through v0.40.0.
  - Immer move style since v0.28.0.
  - v0.50.0 changed move signatures to `({ G, ctx }) => {}`.
- Multiplayer doc: `Local()` runs the master in the browser for pass-and-play with optional `localStorage` persistence. `SocketIO()` runs a remote master. The server takes `games` and `origins`, with `Origins.LOCALHOST` for development. The master is the "single source of authority" and clients do "optimistic updates". The doc does not describe authentication [R51].
- Known limitation: issue #533 (2019-12-22, closed) reports that the MCTS bot did not respect turn limits or legal moves when the state `G` held class instances [R52].

### 4.2 Colyseus

- npm 0.18.5, published 2026-08-28, MIT [R3].
- Blog: 0.18 on 2026-08-20 with client-side prediction, request/response messages, and Schema 5.0. 0.17 on 2026-02-06 with automatic reconnection and `defineServer()`. 0.16 on 2025-02-18 with StateView and experimental WebTransport [R53].
- GitHub: MIT, 7.3k stars, authoritative server, delta-compressed binary state sync, rooms and matchmaking, Node.js and TypeScript [R54].

### 4.3 PeerJS and WebRTC

- npm 1.5.5, published 2025-06-07, MIT [R3].
- FAQ: "PeerJS needs a signaling server to help peers find each other (the 'handshake')." After the handshake, "data flows directly between browsers." A self-hosted PeerServer replaces the cloud server [R55, R56].
- Issue #608 (2019-12-17, closed) describes a LAN problem. The two machines connected to the peer server, but the browsers made no WebRTC offer. The logs showed mDNS `.local` candidates [R57].

### 4.4 Yjs and CRDT

- npm 13.6.32, published 2026-08-04, MIT [R3].
- The ToolJet tic-tac-toe example (2022-03-22) uses `WebrtcProvider` with public signaling servers. The design is decentralized. No central authority validates moves. Peers set state in a `Y.Map` and the CRDT merges concurrent edits [R58].

### 4.5 Which fits "hot seat plus LAN, no accounts"

A CRDT does not fit. A wargame has rules that reject moves. A CRDT merges each edit. Yjs would have to have a different validation layer, and then the CRDT adds nothing.

There is no PeerJS without a server. The FAQ gives the signaling requirement [R55]. A self-hosted PeerServer on the LAN is possible, but it is also a server process.

boardgame.io fits the phase model and the `stages` feature, and `Local()` gives hot seat for free [R51]. The last release is from 2022 and the MCTS bot has a known limitation with class instances in `G` [R3, R52]. The rules must also run in JavaScript for it to work. That does not agree with the Rust engine in section 1.

Recommendation: write the phase and turn sequencer in the Rust engine, because the RL trainer also must have it. For LAN, run a small authoritative host process in the browser tab of the host player, or in a tiny Node or Python process. Transport moves as signed, ordered command records on a plain WebSocket (`ws` 8.21.3, MIT, or `socket.io` 4.8.3, MIT [R3]).

Use Colyseus if the developer wants a framework for rooms, reconnection, and synchronization of game data [R53, R54]. No accounts: a room code is the only credential.

## 5. Deterministic simulation and replay

### 5.1 Facts about built-in generators

- JavaScript `Math.random()`: MDN says that the implementation selects the initial seed, and that the user cannot select it or set it again [R59].
- Python `random`: the 3.14.7 docs say "Python uses the Mersenne Twister as the core generator." The docs promise that "The generator's `random()` method will continue to produce the same sequence when the compatible seeder is given the same seed." [R60]
- The PRNG shootout site says "xorshift128+ is presently used in the JavaScript engines of Chrome, Node.js, Firefox, Safari and Microsoft Edge." [R61]

The two built-in generators are different algorithms. A game that needs the same dice in the browser and in Python must ship its own generator.

### 5.2 Cross-language candidates

- PCG32.
  - The `pcg-c-basic` reference implementation is Apache-2.0 [R62]. The pcg-random.org page describes PCG32 as a 32-bit output generator with a 2^64 period, 16 bytes of internal data, and the XSH-RR output function [R63].
  - Python: `randomgen` 2.3.0 (PyPI, 2025-10-22) has a PCG32 bit generator with two 64-bit internal values and an advance function [R64, R3].
  - JavaScript: `pcg-random` 2.0.1 (npm, 2022-03-25, MIT) is an implementation of PCG32 with a seed and a stream given as two 32-bit parts. Its README does not claim that its output is the same as the C reference [R65, R3].
  - PCG32 must have a 64-bit multiply. In JavaScript this means BigInt or a 32-bit emulation.
- xoshiro128**. The reference C file is CC0, by David Blackman and Sebastiano Vigna, 2018. The header text says "one of our 32-bit all-purpose, rock-solid generators" [R66]. All operations are 32-bit, so a JavaScript port must have only `Math.imul` and the `<<` and `>>>` operators. A Python port must apply a 32-bit mask after each operation.

  bryc's PRNG notes (public domain) list xoshiro128** and say it "has poor randomness in the lower bits". The same notes recommend `sfc32` and `mulberry32` for speed and quality in JavaScript [R67].
- seedrandom 3.0.5 (npm, 2019-09-17, MIT) uses ARC4 by default and bundles alea, xor128, xorshift7, xor4096, tychei, and xorwow [R3, R68]. There is no Python reference for its seed procedure, so it is not a cross-language candidate.

Recommendation: put the generator in the Rust engine. Then the browser and Python get the same generator from the same code, and there is no cross-language question. If a JavaScript or Python port is necessary, pick xoshiro128** for its 32-bit arithmetic, or PCG32 with a BigInt path. In each case, write a golden-vector test: one seed, the first 1,000 outputs, compared in all three languages.

### 5.3 Event-sourced game log and determinism tests

The agent found no fetched page that gives a wargame-specific pattern. These are recommendations, not sourced facts:

- Store the seed and the ordered list of player commands. Do not store dice results. The engine regenerates them.
- Give each command a sequence number and the hash of the state after it. A replay compares hashes at each step and stops at the first mismatch.
- Keep all rules arithmetic in integers. Floats are the usual cause of cross-platform drift.
- Add a fuzz test that plays random legal moves from many seeds. Then replay the log and compare the last hash. Run it in the Rust test suite and again through the PyO3 and WASM bindings.

## 6. Procedural map generation with a hand-drawn look

### 6.1 Constraint and tile methods

- Wave Function Collapse, Maxim Gumin. MIT, C#, 25,300 or more stars. Two models: the overlapping model with NxN patterns and the simple tiled model with adjacency rules and a symmetry system. The README gives a list of ports in C++, Python, Kotlin, Rust, Julia, Go, Haxe, Java, Clojure, Free Pascal, Dart, p5js, and JavaScript. It credits Paul Merrell's 2009 model synthesis thesis [R69].
- JavaScript port `wavefunctioncollapse` by kchapelier. MIT, the two models, version 2.1.0 released 2021-03-27, 525 stars [R70].
- Megan Reddy's fantasy map project (2022-12) uses WFC for map layout, then a hand-drawn render pass with cross-hatching, faded paper, and edge lines. The coast hatching uses "horizontal lines with Sobel/FBM mask". The authors built it in Unity, so the shaders are references, not code for direct use [R71].

### 6.2 Noise and contours

- Red Blob "Making maps with noise functions" (written 2015, updated through 2026-08). Covers octaves, redistribution with `Math.pow(e, exponent)`, islands, biomes, and terraces with `Math.round(e * n) / n`. The terrace step is the contour step for hill levels. The page does not give a code license [R72].
- mapgen4 by Red Blob Games. Apache-2.0, TypeScript, WebGL, with edge-line and contour rendering on a dual-mesh structure of Delaunay and Voronoi cells. The README marks it unmaintained, last updated 2023 [R73].
- Azgaar's Fantasy Map Generator. JavaScript with a move to TypeScript, Vite, SVG and WebGL output, Voronoi and heightmap methods. The repository has a LICENSE file. The agent did not read the license text, so this document makes no license claim [R74].

### 6.3 Geomorphic edge constraints

- Wikipedia describes the Squad Leader boards as "generic geomorphic mapboards, each of which can be aligned to any edge of the same length to any other mapboard", with 40 meters for each hex and four boards: urban, hill, village, rural [R30].
- Hextiles by Sly Gryphon (CC BY-SA 4.0) shows an edge-coding scheme for hex geomorphs. Each edge has a connection code. A tile connects only to a tile with the same edge code [R75]. The same idea works for a wargame. Set the terrain of the boundary hex row on each board edge. Then let WFC or noise fill the inner hexes with that constraint.

### 6.4 Hand-inked rendering tricks

- rough.js 4.6.6 (npm, 2023-11-20, MIT). It makes lines, curves, polygons, circles, and SVG paths in a sketchy style on Canvas and SVG [R3, R76]. It has `roughness` and `bowing` parameters. Fill styles are hachure, solid, zigzag, cross-hatch, dots, sunburst, and dashed. Hachure fills are a good fit for woods and hill shade on 1970s boards.
- Paper grain: a tiled noise texture with multiply blending. The MDN canvas page covers the offscreen pre-render pattern that this requires [R33]. No fetched page gives a recipe for the 1977 Avalon Hill look.

## 7. Fonts and counter art

### 7.1 Typeface sources

The agent could not fetch a page that names the typeface on Avalon Hill counters. The codex99 counter page gave a certificate error, and BoardGameGeek gave HTTP 403. Wikipedia on Redmond Simonsen (SPI art director, 1942 to 2005) records the "physical systems design" philosophy and the move from black-and-white paper maps to full-color die-cut counters, but names no typeface [R77]. Treat the Helvetica or Futura resemblance as an unverified visual judgment.

### 7.2 Open-license alternatives

| Font | License | Source |
|---|---|---|
| Inter (Helvetica-like, neo-grotesque, variable) | SIL OFL 1.1 | rsms/inter [R78], google/fonts `ofl/inter` [R79] |
| Jost (Futura-like, geometric, 9 weights, version 3.7) | SIL OFL | indestructible-type/Jost [R80], google/fonts `ofl/jost` [R81] |
| Liberation Sans (metric compatible with Arial) | SIL OFL 1.1 | liberationfonts [R82] |

Note: the Jost GitHub page says the compiled variable font costs 10 USD or more, while the source is free. The Google Fonts repository has `Jost[wght].ttf` and `OFL.txt` in `ofl/jost`, so the Google build is the one to use [R80, R81].

### 7.3 SVG counters and NATO symbols

- milsymbol 3.0.4 (npm, 2026-03-10, MIT). Pure JavaScript with no dependencies. It outputs SVG and Canvas. It supports MIL-STD-2525C, D, and E, and STANAG APP-6 B, D, and E. The README claims "1000 symbols in less than 20 milliseconds (SVG output)" [R3, R83].
- Counter generation: build each counter as an SVG string from data (nationality color, unit symbol, morale, firepower, range). Rasterize the set into one texture atlas at load time for the WebGL or Canvas path. milsymbol gives the NATO symbol layer. Infantry, machine gun, and leader counters in the 1977 style use simple silhouettes rather than NATO frames. The agent found no open-license silhouette set on a fetched page.

## 8. Build tooling for 2026

Versions from the npm registry on 2026-09-07 [R3]:

- Vite 8.2.2 (2026-08-20, MIT). Vite 8.0 shipped 2026-03-12 with Rolldown as "its single, unified, Rust-based bundler" and must have Node 20.19+ or 22.12+ [R84].
- TypeScript 7.0.2 (2026-07-08, Apache-2.0). InfoQ reports the Go-native compiler at 11.9x faster on the VS Code build (125.7 s to 10.6 s) and notes that 7.0 "ships without a stable programmatic API" until 7.1 [R85].
- Vitest 5.0.0 (2026-09-03, MIT).
- @playwright/test 1.63.0 (2026-09-04, Apache-2.0).
- @tauri-apps/cli 2.11.4 (2026-06-28, Apache-2.0 OR MIT). Electron 44.2.0 (2026-09-04, MIT). Neither is necessary for a browser-first game. Tauri is the smaller alternative if the developer wants a desktop wrapper at a subsequent time.

## References

- [R1] Benchmarks Game, Python 3 versus Node.js. https://benchmarksgame-team.pages.debian.net/benchmarksgame/fastest/python3-node.html
- [R2] gRPC performance best practices. https://grpc.io/docs/guides/performance/
- [R3] npm registry API, queried 2026-09-07 for each package. https://registry.npmjs.org/
- [R4] PyPI JSON API and crates.io API, queried 2026-09-07. https://pypi.org/pypi/maturin/json and https://crates.io/api/v1/crates/pyo3
- [R5] crates.io, wasm-bindgen. https://crates.io/api/v1/crates/wasm-bindgen
- [R6] wasm-pack repository. https://github.com/wasm-bindgen/wasm-pack
- [R7] PyO3 discussion #1935, WASM and Python. https://github.com/PyO3/pyo3/discussions/1935
- [R8] Automerge repository. https://github.com/automerge/automerge
- [R9] automerge-py repository. https://github.com/automerge/automerge-py
- [R10] Ruff pyproject.toml. https://raw.githubusercontent.com/astral-sh/ruff/main/pyproject.toml
- [R11] Ruff ruff_wasm crate. https://github.com/astral-sh/ruff/tree/main/crates/ruff_wasm
- [R12] ypy repository (archived). https://github.com/y-crdt/ypy
- [R13] rlox repository. https://github.com/wojciechkpl/rlox
- [R14] Jangda and others, Not So Fast: Analyzing the Performance of WebAssembly vs. Native Code, 2019. https://arxiv.org/abs/1901.09056
- [R15] Simon Willison, PyO3/Maturin extension modules as WebAssembly wheels for Pyodide, 2026-02-06. https://simonwillison.net/2026/Feb/6/pyo3-pyodide-wasm/
- [R16] FastAPI WebSockets. https://fastapi.tiangolo.com/advanced/websockets/
- [R17] Django Channels documentation. https://channels.readthedocs.io/en/latest/
- [R18] Spheron, RL environments on GPU cloud, 2026-06-09. https://www.spheron.network/blog/rl-environments-gpu-cloud-gymnasium-prime-intellect-verifiers/
- [R19] EnvPool repository. https://github.com/sail-sg/envpool
- [R20] LWN, Pyodide: Python for the browser, 2021-05-11. https://lwn.net/Articles/855875/
- [R21] Pyodide FAQ source. https://raw.githubusercontent.com/pyodide/pyodide/main/docs/usage/faq.md
- [R22] Emscripten ChangeLog. https://raw.githubusercontent.com/emscripten-core/emscripten/main/ChangeLog.md
- [R23] Zig downloads. https://ziglang.org/download/
- [R24] cffi overview. https://cffi.readthedocs.io/en/latest/overview.html
- [R25] Python ctypes documentation. https://docs.python.org/3/library/ctypes.html
- [R26] PufferLib site. https://puffer.ai/
- [R27] PufferLib documentation. https://puffer.ai/docs.html
- [R28] PufferLib repository. https://github.com/PufferAI/PufferLib
- [R29] box2d-wasm repository. https://github.com/Birch-san/box2d-wasm
- [R30] Wikipedia, Squad Leader. https://en.wikipedia.org/wiki/Squad_Leader
- [R31] Apache ECharts handbook, Canvas vs. SVG. https://apache.github.io/echarts-handbook/en/best-practices/canvas-vs-svg/
- [R32] JointJS, SVG versus Canvas, 2025-08-23. https://www.jointjs.com/blog/svg-versus-canvas
- [R33] MDN, Optimizing canvas. https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial/Optimizing_canvas
- [R34] Shirajuki, JS game rendering benchmark. https://github.com/Shirajuki/js-game-rendering-benchmark
- [R35] PixiJS v8 launch post, 2024-03-05. https://pixijs.com/blog/pixi-v8-launches
- [R36] PixiJS 8.16.0 release post, 2026-02-04. https://pixijs.com/blog/8.16.0
- [R37] PixiJS event-system page. https://pixijs.com/8.x/guides/components/events
- [R38] PixiJS performance tips. https://pixijs.com/8.x/guides/concepts/performance-tips
- [R39] Wikipedia, Phaser (game framework). https://en.wikipedia.org/wiki/Phaser_(game_framework)
- [R40] Phaser v4 Release Candidate 4, 2025-05-23. https://phaser.io/news/2025/05/phaser-v4-release-candidate-4
- [R41] MDN, OffscreenCanvas. https://developer.mozilla.org/en-US/docs/Web/API/OffscreenCanvas
- [R42] Red Blob Games, Hexagonal Grids. https://www.redblobgames.com/grids/hexagons/
- [R43] Red Blob Games, hex code page. https://www.redblobgames.com/grids/hexagons/implementation.html
- [R44] Honeycomb repository. https://github.com/flauwekeul/honeycomb
- [R45] zvold, Line of sight on a hexagonal grid, 2010-02-07. http://zvold.blogspot.com/2010/02/line-of-sight-on-hexagonal-grid.html
- [R46] fananek/hex-grid (Swift). https://github.com/fananek/hex-grid
- [R47] euoia/hex-grid.js. https://github.com/euoia/hex-grid.js
- [R48] boardgame.io repository. https://github.com/boardgameio/boardgame.io
- [R49] boardgame.io commit history. https://github.com/boardgameio/boardgame.io/commits/main
- [R50] boardgame.io changelog. https://raw.githubusercontent.com/boardgameio/boardgame.io/main/docs/documentation/CHANGELOG.md
- [R51] boardgame.io multiplayer doc. https://raw.githubusercontent.com/boardgameio/boardgame.io/main/docs/documentation/multiplayer.md
- [R52] boardgame.io issue #533. https://github.com/boardgameio/boardgame.io/issues/533
- [R53] Colyseus blog. https://colyseus.io/blog/
- [R54] Colyseus repository. https://github.com/colyseus/colyseus
- [R55] PeerJS FAQ. https://peerjs.com/client/faq
- [R56] PeerJS repository. https://github.com/peers/peerjs
- [R57] PeerJS issue #608. https://github.com/peers/peerjs/issues/608
- [R58] ToolJet, multiplayer tic-tac-toe with Yjs, 2022-03-22. https://dev.to/tooljet/building-a-realtime-multiplayer-game-using-react-conflict-free-replicated-data-types-crdt-of-yjs-16o7
- [R59] MDN, Math.random(). https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Math/random
- [R60] Python random module, 3.14.7. https://docs.python.org/3/library/random.html
- [R61] Vigna, A PRNG shootout. https://prng.di.unimi.it/
- [R62] pcg-c-basic repository. https://github.com/imneme/pcg-c-basic
- [R63] pcg-random.org, C library usage page. https://www.pcg-random.org/using-pcg-c.html
- [R64] randomgen PCG32. https://bashtage.github.io/randomgen/bit_generators/pcg32.html
- [R65] thomcc/pcg-random. https://github.com/thomcc/pcg-random
- [R66] xoshiro128** reference C. https://prng.di.unimi.it/xoshiro128starstar.c
- [R67] bryc, PRNGs.md. https://github.com/bryc/code/blob/master/jshash/PRNGs.md
- [R68] seedrandom repository. https://github.com/davidbau/seedrandom
- [R69] mxgmn/WaveFunctionCollapse. https://github.com/mxgmn/WaveFunctionCollapse
- [R70] kchapelier/wavefunctioncollapse. https://github.com/kchapelier/wavefunctioncollapse
- [R71] Megan Reddy, Fantasy Map Generator, 2022-12. https://meganr28.github.io/code/fantasymap/
- [R72] Red Blob Games, Making maps with noise functions. https://www.redblobgames.com/maps/terrain-from-noise/
- [R73] mapgen4 repository. https://github.com/redblobgames/mapgen4
- [R74] Azgaar Fantasy Map Generator. https://github.com/Azgaar/Fantasy-Map-Generator
- [R75] sgryphon/hextiles. https://github.com/sgryphon/hextiles
- [R76] rough.js. https://roughjs.com/
- [R77] Wikipedia, Redmond A. Simonsen. https://en.wikipedia.org/wiki/Redmond_A._Simonsen
- [R78] rsms/inter. https://github.com/rsms/inter
- [R79] google/fonts ofl/inter. https://github.com/google/fonts/tree/main/ofl/inter
- [R80] indestructible-type/Jost. https://github.com/indestructible-type/Jost
- [R81] google/fonts ofl/jost. https://github.com/google/fonts/tree/main/ofl/jost
- [R82] Liberation fonts. https://github.com/liberationfonts/liberation-fonts
- [R83] milsymbol repository. https://github.com/spatialillusions/milsymbol
- [R84] Vite 8.0 announcement, 2026-03-12. https://vite.dev/blog/announcing-vite8
- [R85] InfoQ, TypeScript 7.0 released. https://www.infoq.com/news/2026/08/typescript-7-released/

## Pages that did not open

These pages gave errors. No claim in this document comes from them.

- npmjs.com package pages (HTTP 403). The agent used the registry API as the alternative.
- pyodide.org roadmap and FAQ (HTTP 403). The agent used the GitHub source as the alternative.
- blog.pyodide.org (HTTP 403).
- codex99.com counter page (certificate expired).
- boardgamegeek.com thread (HTTP 403).
- discuss.yjs.dev (certificate expired).
- The Stanford HexLOS page (certificate mismatch).
- Google Fonts specimen pages (no content).
