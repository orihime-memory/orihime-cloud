import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";

window.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("vrm-layer");
  if (!container) {
    console.error("vrm-layer が見つからない");
    return;
  }

  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();

  const camera = new THREE.PerspectiveCamera(
    30,
    window.innerWidth / window.innerHeight,
    0.1,
    100
  );

  const FIXED_CAMERA = { x: 0.56, y: 0.23, z: 1.8 };
  const FIXED_TARGET = { x: -0.21, y: 0.35, z: 0.00 };

  camera.position.set(FIXED_CAMERA.x, FIXED_CAMERA.y, FIXED_CAMERA.z);
  camera.lookAt(FIXED_TARGET.x, FIXED_TARGET.y, FIXED_TARGET.z);

  const light1 = new THREE.HemisphereLight(0xffffff, 0x444444, 1.5);
  scene.add(light1);

  const light2 = new THREE.DirectionalLight(0xffffff, 1.1);
  light2.position.set(1.5, 3, 2.2);
  scene.add(light2);

  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));

  let currentVrm = null;
  let blinkUntil = 0;
  let nextBlinkAt = performance.now() + 1200;

  function applyIdlePose(vrm) {
    if (!vrm || !vrm.humanoid) return;

    const leftUpperArm =
      vrm.humanoid.getNormalizedBoneNode("leftUpperArm") ||
      vrm.humanoid.getRawBoneNode("leftUpperArm");

    const rightUpperArm =
      vrm.humanoid.getNormalizedBoneNode("rightUpperArm") ||
      vrm.humanoid.getRawBoneNode("rightUpperArm");

    const leftLowerArm =
      vrm.humanoid.getNormalizedBoneNode("leftLowerArm") ||
      vrm.humanoid.getRawBoneNode("leftLowerArm");

    const rightLowerArm =
      vrm.humanoid.getNormalizedBoneNode("rightLowerArm") ||
      vrm.humanoid.getRawBoneNode("rightLowerArm");

    const leftHand =
      vrm.humanoid.getNormalizedBoneNode("leftHand") ||
      vrm.humanoid.getRawBoneNode("leftHand");

    const rightHand =
      vrm.humanoid.getNormalizedBoneNode("rightHand") ||
      vrm.humanoid.getRawBoneNode("rightHand");

    if (leftUpperArm) {
      leftUpperArm.rotation.z = 1.1;
      leftUpperArm.rotation.y = 0.7;
    }
    if (rightUpperArm) {
      rightUpperArm.rotation.z = -1.1;
      rightUpperArm.rotation.y = -0.7;
    }

    if (leftLowerArm) {
      leftLowerArm.rotation.z = 0.18;
    }
    if (rightLowerArm) {
      rightLowerArm.rotation.z = -0.2;
    }

    if (leftHand) {
      leftHand.rotation.z = 0.35;
    }
    if (rightHand) {
      rightHand.rotation.z = -0.35;
    }
  }

  loader.load("/static/vrm/orihime.vrm", (gltf) => {
    const vrm = gltf.userData.vrm;
    if (!vrm) {
      console.error("VRMの読み込みに失敗");
      return;
    }

    VRMUtils.rotateVRM0(vrm);
    currentVrm = vrm;

    vrm.scene.position.set(-0.2, -0.8, 0);
    vrm.scene.rotation.y = Math.PI;

    applyIdlePose(vrm);
    scene.add(vrm.scene);
  });

  const clock = new THREE.Clock();

  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  function animate() {
    requestAnimationFrame(animate);

    if (currentVrm) {
      const delta = clock.getDelta();
      currentVrm.update(delta);

      const now = performance.now();
      const t = now * 0.001;

      currentVrm.scene.rotation.y = Math.PI + Math.sin(t * 0.9) * 0.035;
      currentVrm.scene.position.y = -0.8 + Math.sin(t * 0.8) * 0.003;

      const em = currentVrm.expressionManager;
      if (em && em.setValue) {
        if (now >= nextBlinkAt) {
          blinkUntil = now + 120;
          nextBlinkAt = now + 1800 + Math.random() * 2600;
        }

        let blink = 0;
        if (now < blinkUntil) {
          const p = (blinkUntil - now) / 120;
          blink = p < 0.5 ? 1 - p * 2 : (p - 0.5) * 2;
        }

        em.setValue("blink", blink);
        em.setValue("blinkLeft", blink);
        em.setValue("blinkRight", blink);

        const audio = document.getElementById("tts-audio");
        let mouth = 0;
        if (audio && !audio.paused && !audio.ended) {
          const speed = 8 + Math.sin(t * 0.7) * 2;
          mouth = 0.10 + ((Math.sin(t * speed) + 1) / 2) * 0.28;
        }

        em.setValue("aa", mouth);
        em.setValue("oh", mouth * 0.35);
      }
    }

    camera.lookAt(FIXED_TARGET.x, FIXED_TARGET.y, FIXED_TARGET.z);
    renderer.render(scene, camera);
  }

  animate();
});