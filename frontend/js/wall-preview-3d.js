/* wall-preview-3d.js — the 3D wall point cloud.
 *
 * Replaces the old matplotlib mplot3d dialog. Uses the vendored three.js ESM
 * build (frontend/js/vendor/) so the app stays self-hosted — no CDN.
 * OrbitControls ships as a separate add-on, so the drag/zoom handling here is
 * hand-rolled: it is only a few dozen lines for the orbit we actually need.
 */

import * as THREE from './vendor/three.module.min.js';

/* Deep primary -> light blue -> cyan -> amber -> salmon: the palette's own
   hues, ordered so low values read cool and high values read hot. */
function colorRamp(t) {
  const stops = [
    [0.000, [0.000, 0.322, 0.533]],   // #005288 primary
    [0.250, [0.612, 0.792, 1.000]],   // #9CCAFF light blue
    [0.500, [0.000, 0.820, 1.000]],   // #00D1FF secondary
    [0.750, [1.000, 0.722, 0.000]],   // #FFB800 tertiary
    [1.000, [1.000, 0.706, 0.671]],   // #FFB4AB salmon
  ];
  const x = Math.min(Math.max(t, 0), 1);
  for (let i = 1; i < stops.length; i += 1) {
    if (x <= stops[i][0]) {
      const [t0, c0] = stops[i - 1];
      const [t1, c1] = stops[i];
      const f = (x - t0) / (t1 - t0 || 1);
      return c0.map((c, j) => c + f * (c1[j] - c));
    }
  }
  return stops.at(-1)[1];
}

export class WallPreview3D {
  constructor(container) {
    this.container = container;
    this.renderer = null;
    this.frame = null;
    // Spherical camera position around the cloud centre.
    this.orbit = { theta: 0.9, phi: 1.15, radius: 1 };
    this.dragging = null;
  }

  ensureScene() {
    if (this.renderer) return;

    const width = this.container.clientWidth || 640;
    const height = this.container.clientHeight || 420;

    this.scene = new THREE.Scene();
    const styles = getComputedStyle(document.documentElement);
    this.scene.background = new THREE.Color(
      styles.getPropertyValue('--bg-inset').trim() || '#07090B',
    );

    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.001, 5000);
    this.target = new THREE.Vector3();

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(width, height);
    this.container.replaceChildren(this.renderer.domElement);

    this.bindControls(this.renderer.domElement);
  }

  bindControls(canvas) {
    canvas.style.touchAction = 'none';
    canvas.style.cursor = 'grab';

    canvas.addEventListener('pointerdown', (e) => {
      this.dragging = { x: e.clientX, y: e.clientY };
      canvas.setPointerCapture(e.pointerId);
      canvas.style.cursor = 'grabbing';
    });
    canvas.addEventListener('pointermove', (e) => {
      if (!this.dragging) return;
      const dx = e.clientX - this.dragging.x;
      const dy = e.clientY - this.dragging.y;
      this.dragging = { x: e.clientX, y: e.clientY };
      this.orbit.theta -= dx * 0.006;
      // Clamp off the poles so the view never flips.
      this.orbit.phi = Math.min(Math.max(this.orbit.phi - dy * 0.006, 0.05), Math.PI - 0.05);
      this.requestRender();
    });
    const endDrag = (e) => {
      this.dragging = null;
      canvas.style.cursor = 'grab';
      if (e.pointerId != null && canvas.hasPointerCapture?.(e.pointerId)) {
        canvas.releasePointerCapture(e.pointerId);
      }
    };
    canvas.addEventListener('pointerup', endDrag);
    canvas.addEventListener('pointercancel', endDrag);

    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      this.orbit.radius *= e.deltaY > 0 ? 1.1 : 0.9;
      this.orbit.radius = Math.min(Math.max(this.orbit.radius, this.minRadius || 0.01),
        (this.maxRadius || 1e4));
      this.requestRender();
    }, { passive: false });
  }

  /** Build the cloud. `values` (optional) colour-maps the points. */
  setPoints(x, y, z, values, label) {
    this.ensureScene();

    const count = x.length;
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);

    let finiteValues = null;
    let lo = 0;
    let hi = 1;
    if (values && values.length === count) {
      finiteValues = values.filter((v) => typeof v === 'number' && Number.isFinite(v));
      if (finiteValues.length) {
        lo = Math.min(...finiteValues);
        hi = Math.max(...finiteValues);
      }
    }
    const span = hi - lo || 1;

    const box = new THREE.Box3();
    const point = new THREE.Vector3();

    for (let i = 0; i < count; i += 1) {
      positions[i * 3] = x[i];
      positions[i * 3 + 1] = y[i];
      positions[i * 3 + 2] = z[i];
      point.set(x[i], y[i], z[i]);
      box.expandByPoint(point);

      let rgb = [0.612, 0.792, 1.000];
      if (finiteValues && finiteValues.length) {
        const v = values[i];
        rgb = Number.isFinite(v) ? colorRamp((v - lo) / span) : [0.42, 0.44, 0.53];
      }
      colors[i * 3] = rgb[0];
      colors[i * 3 + 1] = rgb[1];
      colors[i * 3 + 2] = rgb[2];
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const size = box.getSize(new THREE.Vector3());
    const extent = Math.max(size.x, size.y, size.z) || 1;

    const material = new THREE.PointsMaterial({
      size: extent * 0.006,
      vertexColors: true,
      sizeAttenuation: true,
    });

    if (this.points) {
      this.points.geometry.dispose();
      this.points.material.dispose();
      this.scene.remove(this.points);
    }
    this.points = new THREE.Points(geometry, material);
    this.scene.add(this.points);

    // Engine axis, so the revolve is readable at a glance.
    if (this.axis) this.scene.remove(this.axis);
    const axisGeom = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(box.min.x, 0, 0),
      new THREE.Vector3(box.max.x, 0, 0),
    ]);
    this.axis = new THREE.Line(
      axisGeom,
      new THREE.LineBasicMaterial({ color: 0xFFB4AB, transparent: true, opacity: 0.55 }),
    );
    this.scene.add(this.axis);

    box.getCenter(this.target);
    this.orbit.radius = extent * 2.1;
    this.minRadius = extent * 0.15;
    this.maxRadius = extent * 12;

    this.range = finiteValues && finiteValues.length ? { lo, hi, label } : null;
    this.resize();
    this.requestRender();
  }

  resize() {
    if (!this.renderer) return;
    const width = this.container.clientWidth || 640;
    const height = this.container.clientHeight || 420;
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.requestRender();
  }

  requestRender() {
    if (!this.renderer || this.frame) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = null;
      const { theta, phi, radius } = this.orbit;
      this.camera.position.set(
        this.target.x + radius * Math.sin(phi) * Math.cos(theta),
        this.target.y + radius * Math.cos(phi),
        this.target.z + radius * Math.sin(phi) * Math.sin(theta),
      );
      this.camera.lookAt(this.target);
      this.renderer.render(this.scene, this.camera);
    });
  }

  dispose() {
    if (this.frame) cancelAnimationFrame(this.frame);
    this.points?.geometry.dispose();
    this.points?.material.dispose();
    this.renderer?.dispose();
    this.renderer = null;
    this.points = null;
  }
}
