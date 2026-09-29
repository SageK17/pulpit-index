// Friends backend for the GitHub Pages build (the claude.ai build uses the page's own db + user capabilities).
// Exposes the same small surface the app already uses: db.doc(path) / db.collection(path).where().limit(),
// with get / set / update / onSnapshot, plus profiles(ids), onUser(cb), signIn(), signOut().
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js";
import { getAuth, GoogleAuthProvider, signInWithPopup, signInWithRedirect, onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js";
import { getFirestore, doc, collection, query, where, limit, onSnapshot, getDoc, getDocs, setDoc, updateDoc } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js";

try {
  const app = initializeApp(window.PULPIT_FIREBASE);
  const auth = getAuth(app);
  const fs = getFirestore(app);

  const snapDoc = (s) => ({ id: s.id, exists: s.exists(), data: () => s.data() });
  const snapQuery = (q) => ({ docs: q.docs.map(snapDoc), empty: q.empty, size: q.size });
  // The app treats "invalid_argument" as "you may not write here"; map Firestore's refusal onto it.
  const wrapErr = (e) => ({ code: e && e.code === "permission-denied" ? "invalid_argument" : (e && e.code) || "unavailable", message: (e && e.message) || "" });
  const rethrow = (e) => { throw wrapErr(e); };

  const docRef = (path) => {
    const r = doc(fs, path);
    return {
      id: r.id, path,
      get: () => getDoc(r).then(snapDoc, rethrow),
      set: (d) => setDoc(r, d).catch(rethrow),
      update: (d) => updateDoc(r, d).catch(rethrow),
      onSnapshot: (next, err) => onSnapshot(r, (s) => next(snapDoc(s)), (e) => err && err(wrapErr(e))),
    };
  };
  const queryRef = (path, cons) => {
    const build = () => query(collection(fs, path), ...cons);
    return {
      where: (f, op, v) => queryRef(path, cons.concat([where(f, op, v)])),
      limit: (n) => queryRef(path, cons.concat([limit(n)])),
      get: () => getDocs(build()).then(snapQuery, rethrow),
      onSnapshot: (next, err) => onSnapshot(build(), (q) => next(snapQuery(q)), (e) => err && err(wrapErr(e))),
    };
  };
  const db = { doc: docRef, collection: (p) => queryRef(p, []) };

  const hue = (id) => { let h = 0; for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0; return `hsl(${h % 360} 42% 44%)`; };
  const cache = {};
  const profiles = async (ids) => {
    const out = {};
    await Promise.all([...new Set([].concat(ids))].map(async (id) => {
      const hit = cache[id];
      if (!hit || Date.now() - hit.t > 60000) {
        let p = { id, name: "", avatarUrl: "", color: hue(id), isMe: !!(auth.currentUser && auth.currentUser.uid === id) };
        try {
          const s = await getDoc(doc(fs, "members/" + id));
          const x = s.exists() ? s.data() : {};
          p.name = typeof x.name === "string" ? x.name.slice(0, 60) : "";
          p.avatarUrl = typeof x.photo === "string" && /^https:\/\//.test(x.photo) ? x.photo : "";
        } catch (e) { /* unreadable: render as "Someone" */ }
        cache[id] = { t: Date.now(), p };
      }
      out[id] = cache[id].p;
    }));
    return out;
  };

  const provider = new GoogleAuthProvider();
  window.PULPIT_BACKEND_RESOLVE({
    kind: "firebase",
    db,
    profiles,
    onUser: (cb) => onAuthStateChanged(auth, (u) => cb(u ? { id: u.uid, name: u.displayName || "", avatarUrl: u.photoURL || "", email: null } : null)),
    signIn: () => signInWithPopup(auth, provider).catch((e) => {
      if (e && (e.code === "auth/popup-blocked" || e.code === "auth/operation-not-supported-in-this-environment")) return signInWithRedirect(auth, provider);
      throw e;
    }),
    signOut: () => signOut(auth),
  });
} catch (e) {
  window.PULPIT_BACKEND_REJECT(e);
}
