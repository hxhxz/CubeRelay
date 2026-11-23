"use strict";
(() => {
  var __create = Object.create;
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __getProtoOf = Object.getPrototypeOf;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __commonJS = (cb, mod) => function __require() {
    return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
    // If the importer is in node compatibility mode or this is not an ESM
    // file that has been converted to a CommonJS file using a Babel-
    // compatible transform (i.e. "__esModule" has not been set), then set
    // "default" to the CommonJS "module.exports" for node compatibility.
    isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
    mod
  ));

  // web/console/node_modules/react/cjs/react.production.min.js
  var require_react_production_min = __commonJS({
    "web/console/node_modules/react/cjs/react.production.min.js"(exports) {
      "use strict";
      var l = Symbol.for("react.element");
      var n = Symbol.for("react.portal");
      var p = Symbol.for("react.fragment");
      var q = Symbol.for("react.strict_mode");
      var r = Symbol.for("react.profiler");
      var t = Symbol.for("react.provider");
      var u = Symbol.for("react.context");
      var v = Symbol.for("react.forward_ref");
      var w = Symbol.for("react.suspense");
      var x = Symbol.for("react.memo");
      var y = Symbol.for("react.lazy");
      var z = Symbol.iterator;
      function A(a) {
        if (null === a || "object" !== typeof a) return null;
        a = z && a[z] || a["@@iterator"];
        return "function" === typeof a ? a : null;
      }
      var B = { isMounted: function() {
        return false;
      }, enqueueForceUpdate: function() {
      }, enqueueReplaceState: function() {
      }, enqueueSetState: function() {
      } };
      var C = Object.assign;
      var D = {};
      function E(a, b, e) {
        this.props = a;
        this.context = b;
        this.refs = D;
        this.updater = e || B;
      }
      E.prototype.isReactComponent = {};
      E.prototype.setState = function(a, b) {
        if ("object" !== typeof a && "function" !== typeof a && null != a) throw Error("setState(...): takes an object of state variables to update or a function which returns an object of state variables.");
        this.updater.enqueueSetState(this, a, b, "setState");
      };
      E.prototype.forceUpdate = function(a) {
        this.updater.enqueueForceUpdate(this, a, "forceUpdate");
      };
      function F() {
      }
      F.prototype = E.prototype;
      function G(a, b, e) {
        this.props = a;
        this.context = b;
        this.refs = D;
        this.updater = e || B;
      }
      var H = G.prototype = new F();
      H.constructor = G;
      C(H, E.prototype);
      H.isPureReactComponent = true;
      var I = Array.isArray;
      var J = Object.prototype.hasOwnProperty;
      var K = { current: null };
      var L = { key: true, ref: true, __self: true, __source: true };
      function M(a, b, e) {
        var d, c = {}, k = null, h = null;
        if (null != b) for (d in void 0 !== b.ref && (h = b.ref), void 0 !== b.key && (k = "" + b.key), b) J.call(b, d) && !L.hasOwnProperty(d) && (c[d] = b[d]);
        var g = arguments.length - 2;
        if (1 === g) c.children = e;
        else if (1 < g) {
          for (var f = Array(g), m = 0; m < g; m++) f[m] = arguments[m + 2];
          c.children = f;
        }
        if (a && a.defaultProps) for (d in g = a.defaultProps, g) void 0 === c[d] && (c[d] = g[d]);
        return { $$typeof: l, type: a, key: k, ref: h, props: c, _owner: K.current };
      }
      function N(a, b) {
        return { $$typeof: l, type: a.type, key: b, ref: a.ref, props: a.props, _owner: a._owner };
      }
      function O(a) {
        return "object" === typeof a && null !== a && a.$$typeof === l;
      }
      function escape(a) {
        var b = { "=": "=0", ":": "=2" };
        return "$" + a.replace(/[=:]/g, function(a2) {
          return b[a2];
        });
      }
      var P = /\/+/g;
      function Q(a, b) {
        return "object" === typeof a && null !== a && null != a.key ? escape("" + a.key) : b.toString(36);
      }
      function R(a, b, e, d, c) {
        var k = typeof a;
        if ("undefined" === k || "boolean" === k) a = null;
        var h = false;
        if (null === a) h = true;
        else switch (k) {
          case "string":
          case "number":
            h = true;
            break;
          case "object":
            switch (a.$$typeof) {
              case l:
              case n:
                h = true;
            }
        }
        if (h) return h = a, c = c(h), a = "" === d ? "." + Q(h, 0) : d, I(c) ? (e = "", null != a && (e = a.replace(P, "$&/") + "/"), R(c, b, e, "", function(a2) {
          return a2;
        })) : null != c && (O(c) && (c = N(c, e + (!c.key || h && h.key === c.key ? "" : ("" + c.key).replace(P, "$&/") + "/") + a)), b.push(c)), 1;
        h = 0;
        d = "" === d ? "." : d + ":";
        if (I(a)) for (var g = 0; g < a.length; g++) {
          k = a[g];
          var f = d + Q(k, g);
          h += R(k, b, e, f, c);
        }
        else if (f = A(a), "function" === typeof f) for (a = f.call(a), g = 0; !(k = a.next()).done; ) k = k.value, f = d + Q(k, g++), h += R(k, b, e, f, c);
        else if ("object" === k) throw b = String(a), Error("Objects are not valid as a React child (found: " + ("[object Object]" === b ? "object with keys {" + Object.keys(a).join(", ") + "}" : b) + "). If you meant to render a collection of children, use an array instead.");
        return h;
      }
      function S(a, b, e) {
        if (null == a) return a;
        var d = [], c = 0;
        R(a, d, "", "", function(a2) {
          return b.call(e, a2, c++);
        });
        return d;
      }
      function T(a) {
        if (-1 === a._status) {
          var b = a._result;
          b = b();
          b.then(function(b2) {
            if (0 === a._status || -1 === a._status) a._status = 1, a._result = b2;
          }, function(b2) {
            if (0 === a._status || -1 === a._status) a._status = 2, a._result = b2;
          });
          -1 === a._status && (a._status = 0, a._result = b);
        }
        if (1 === a._status) return a._result.default;
        throw a._result;
      }
      var U = { current: null };
      var V = { transition: null };
      var W = { ReactCurrentDispatcher: U, ReactCurrentBatchConfig: V, ReactCurrentOwner: K };
      function X2() {
        throw Error("act(...) is not supported in production builds of React.");
      }
      exports.Children = { map: S, forEach: function(a, b, e) {
        S(a, function() {
          b.apply(this, arguments);
        }, e);
      }, count: function(a) {
        var b = 0;
        S(a, function() {
          b++;
        });
        return b;
      }, toArray: function(a) {
        return S(a, function(a2) {
          return a2;
        }) || [];
      }, only: function(a) {
        if (!O(a)) throw Error("React.Children.only expected to receive a single React element child.");
        return a;
      } };
      exports.Component = E;
      exports.Fragment = p;
      exports.Profiler = r;
      exports.PureComponent = G;
      exports.StrictMode = q;
      exports.Suspense = w;
      exports.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED = W;
      exports.act = X2;
      exports.cloneElement = function(a, b, e) {
        if (null === a || void 0 === a) throw Error("React.cloneElement(...): The argument must be a React element, but you passed " + a + ".");
        var d = C({}, a.props), c = a.key, k = a.ref, h = a._owner;
        if (null != b) {
          void 0 !== b.ref && (k = b.ref, h = K.current);
          void 0 !== b.key && (c = "" + b.key);
          if (a.type && a.type.defaultProps) var g = a.type.defaultProps;
          for (f in b) J.call(b, f) && !L.hasOwnProperty(f) && (d[f] = void 0 === b[f] && void 0 !== g ? g[f] : b[f]);
        }
        var f = arguments.length - 2;
        if (1 === f) d.children = e;
        else if (1 < f) {
          g = Array(f);
          for (var m = 0; m < f; m++) g[m] = arguments[m + 2];
          d.children = g;
        }
        return { $$typeof: l, type: a.type, key: c, ref: k, props: d, _owner: h };
      };
      exports.createContext = function(a) {
        a = { $$typeof: u, _currentValue: a, _currentValue2: a, _threadCount: 0, Provider: null, Consumer: null, _defaultValue: null, _globalName: null };
        a.Provider = { $$typeof: t, _context: a };
        return a.Consumer = a;
      };
      exports.createElement = M;
      exports.createFactory = function(a) {
        var b = M.bind(null, a);
        b.type = a;
        return b;
      };
      exports.createRef = function() {
        return { current: null };
      };
      exports.forwardRef = function(a) {
        return { $$typeof: v, render: a };
      };
      exports.isValidElement = O;
      exports.lazy = function(a) {
        return { $$typeof: y, _payload: { _status: -1, _result: a }, _init: T };
      };
      exports.memo = function(a, b) {
        return { $$typeof: x, type: a, compare: void 0 === b ? null : b };
      };
      exports.startTransition = function(a) {
        var b = V.transition;
        V.transition = {};
        try {
          a();
        } finally {
          V.transition = b;
        }
      };
      exports.unstable_act = X2;
      exports.useCallback = function(a, b) {
        return U.current.useCallback(a, b);
      };
      exports.useContext = function(a) {
        return U.current.useContext(a);
      };
      exports.useDebugValue = function() {
      };
      exports.useDeferredValue = function(a) {
        return U.current.useDeferredValue(a);
      };
      exports.useEffect = function(a, b) {
        return U.current.useEffect(a, b);
      };
      exports.useId = function() {
        return U.current.useId();
      };
      exports.useImperativeHandle = function(a, b, e) {
        return U.current.useImperativeHandle(a, b, e);
      };
      exports.useInsertionEffect = function(a, b) {
        return U.current.useInsertionEffect(a, b);
      };
      exports.useLayoutEffect = function(a, b) {
        return U.current.useLayoutEffect(a, b);
      };
      exports.useMemo = function(a, b) {
        return U.current.useMemo(a, b);
      };
      exports.useReducer = function(a, b, e) {
        return U.current.useReducer(a, b, e);
      };
      exports.useRef = function(a) {
        return U.current.useRef(a);
      };
      exports.useState = function(a) {
        return U.current.useState(a);
      };
      exports.useSyncExternalStore = function(a, b, e) {
        return U.current.useSyncExternalStore(a, b, e);
      };
      exports.useTransition = function() {
        return U.current.useTransition();
      };
      exports.version = "18.3.1";
    }
  });

  // web/console/node_modules/react/index.js
  var require_react = __commonJS({
    "web/console/node_modules/react/index.js"(exports, module) {
      "use strict";
      if (true) {
        module.exports = require_react_production_min();
      } else {
        module.exports = null;
      }
    }
  });

  // web/console/node_modules/scheduler/cjs/scheduler.production.min.js
  var require_scheduler_production_min = __commonJS({
    "web/console/node_modules/scheduler/cjs/scheduler.production.min.js"(exports) {
      "use strict";
      function f(a, b) {
        var c = a.length;
        a.push(b);
        a: for (; 0 < c; ) {
          var d = c - 1 >>> 1, e = a[d];
          if (0 < g(e, b)) a[d] = b, a[c] = e, c = d;
          else break a;
        }
      }
      function h(a) {
        return 0 === a.length ? null : a[0];
      }
      function k(a) {
        if (0 === a.length) return null;
        var b = a[0], c = a.pop();
        if (c !== b) {
          a[0] = c;
          a: for (var d = 0, e = a.length, w = e >>> 1; d < w; ) {
            var m = 2 * (d + 1) - 1, C = a[m], n = m + 1, x = a[n];
            if (0 > g(C, c)) n < e && 0 > g(x, C) ? (a[d] = x, a[n] = c, d = n) : (a[d] = C, a[m] = c, d = m);
            else if (n < e && 0 > g(x, c)) a[d] = x, a[n] = c, d = n;
            else break a;
          }
        }
        return b;
      }
      function g(a, b) {
        var c = a.sortIndex - b.sortIndex;
        return 0 !== c ? c : a.id - b.id;
      }
      if ("object" === typeof performance && "function" === typeof performance.now) {
        l = performance;
        exports.unstable_now = function() {
          return l.now();
        };
      } else {
        p = Date, q = p.now();
        exports.unstable_now = function() {
          return p.now() - q;
        };
      }
      var l;
      var p;
      var q;
      var r = [];
      var t = [];
      var u = 1;
      var v = null;
      var y = 3;
      var z = false;
      var A = false;
      var B = false;
      var D = "function" === typeof setTimeout ? setTimeout : null;
      var E = "function" === typeof clearTimeout ? clearTimeout : null;
      var F = "undefined" !== typeof setImmediate ? setImmediate : null;
      "undefined" !== typeof navigator && void 0 !== navigator.scheduling && void 0 !== navigator.scheduling.isInputPending && navigator.scheduling.isInputPending.bind(navigator.scheduling);
      function G(a) {
        for (var b = h(t); null !== b; ) {
          if (null === b.callback) k(t);
          else if (b.startTime <= a) k(t), b.sortIndex = b.expirationTime, f(r, b);
          else break;
          b = h(t);
        }
      }
      function H(a) {
        B = false;
        G(a);
        if (!A) if (null !== h(r)) A = true, I(J);
        else {
          var b = h(t);
          null !== b && K(H, b.startTime - a);
        }
      }
      function J(a, b) {
        A = false;
        B && (B = false, E(L), L = -1);
        z = true;
        var c = y;
        try {
          G(b);
          for (v = h(r); null !== v && (!(v.expirationTime > b) || a && !M()); ) {
            var d = v.callback;
            if ("function" === typeof d) {
              v.callback = null;
              y = v.priorityLevel;
              var e = d(v.expirationTime <= b);
              b = exports.unstable_now();
              "function" === typeof e ? v.callback = e : v === h(r) && k(r);
              G(b);
            } else k(r);
            v = h(r);
          }
          if (null !== v) var w = true;
          else {
            var m = h(t);
            null !== m && K(H, m.startTime - b);
            w = false;
          }
          return w;
        } finally {
          v = null, y = c, z = false;
        }
      }
      var N = false;
      var O = null;
      var L = -1;
      var P = 5;
      var Q = -1;
      function M() {
        return exports.unstable_now() - Q < P ? false : true;
      }
      function R() {
        if (null !== O) {
          var a = exports.unstable_now();
          Q = a;
          var b = true;
          try {
            b = O(true, a);
          } finally {
            b ? S() : (N = false, O = null);
          }
        } else N = false;
      }
      var S;
      if ("function" === typeof F) S = function() {
        F(R);
      };
      else if ("undefined" !== typeof MessageChannel) {
        T = new MessageChannel(), U = T.port2;
        T.port1.onmessage = R;
        S = function() {
          U.postMessage(null);
        };
      } else S = function() {
        D(R, 0);
      };
      var T;
      var U;
      function I(a) {
        O = a;
        N || (N = true, S());
      }
      function K(a, b) {
        L = D(function() {
          a(exports.unstable_now());
        }, b);
      }
      exports.unstable_IdlePriority = 5;
      exports.unstable_ImmediatePriority = 1;
      exports.unstable_LowPriority = 4;
      exports.unstable_NormalPriority = 3;
      exports.unstable_Profiling = null;
      exports.unstable_UserBlockingPriority = 2;
      exports.unstable_cancelCallback = function(a) {
        a.callback = null;
      };
      exports.unstable_continueExecution = function() {
        A || z || (A = true, I(J));
      };
      exports.unstable_forceFrameRate = function(a) {
        0 > a || 125 < a ? console.error("forceFrameRate takes a positive int between 0 and 125, forcing frame rates higher than 125 fps is not supported") : P = 0 < a ? Math.floor(1e3 / a) : 5;
      };
      exports.unstable_getCurrentPriorityLevel = function() {
        return y;
      };
      exports.unstable_getFirstCallbackNode = function() {
        return h(r);
      };
      exports.unstable_next = function(a) {
        switch (y) {
          case 1:
          case 2:
          case 3:
            var b = 3;
            break;
          default:
            b = y;
        }
        var c = y;
        y = b;
        try {
          return a();
        } finally {
          y = c;
        }
      };
      exports.unstable_pauseExecution = function() {
      };
      exports.unstable_requestPaint = function() {
      };
      exports.unstable_runWithPriority = function(a, b) {
        switch (a) {
          case 1:
          case 2:
          case 3:
          case 4:
          case 5:
            break;
          default:
            a = 3;
        }
        var c = y;
        y = a;
        try {
          return b();
        } finally {
          y = c;
        }
      };
      exports.unstable_scheduleCallback = function(a, b, c) {
        var d = exports.unstable_now();
        "object" === typeof c && null !== c ? (c = c.delay, c = "number" === typeof c && 0 < c ? d + c : d) : c = d;
        switch (a) {
          case 1:
            var e = -1;
            break;
          case 2:
            e = 250;
            break;
          case 5:
            e = 1073741823;
            break;
          case 4:
            e = 1e4;
            break;
          default:
            e = 5e3;
        }
        e = c + e;
        a = { id: u++, callback: b, priorityLevel: a, startTime: c, expirationTime: e, sortIndex: -1 };
        c > d ? (a.sortIndex = c, f(t, a), null === h(r) && a === h(t) && (B ? (E(L), L = -1) : B = true, K(H, c - d))) : (a.sortIndex = e, f(r, a), A || z || (A = true, I(J)));
        return a;
      };
      exports.unstable_shouldYield = M;
      exports.unstable_wrapCallback = function(a) {
        var b = y;
        return function() {
          var c = y;
          y = b;
          try {
            return a.apply(this, arguments);
          } finally {
            y = c;
          }
        };
      };
    }
  });

  // web/console/node_modules/scheduler/index.js
  var require_scheduler = __commonJS({
    "web/console/node_modules/scheduler/index.js"(exports, module) {
      "use strict";
      if (true) {
        module.exports = require_scheduler_production_min();
      } else {
        module.exports = null;
      }
    }
  });

  // web/console/node_modules/react-dom/cjs/react-dom.production.min.js
  var require_react_dom_production_min = __commonJS({
    "web/console/node_modules/react-dom/cjs/react-dom.production.min.js"(exports) {
      "use strict";
      var aa = require_react();
      var ca = require_scheduler();
      function p(a) {
        for (var b = "https://reactjs.org/docs/error-decoder.html?invariant=" + a, c = 1; c < arguments.length; c++) b += "&args[]=" + encodeURIComponent(arguments[c]);
        return "Minified React error #" + a + "; visit " + b + " for the full message or use the non-minified dev environment for full errors and additional helpful warnings.";
      }
      var da = /* @__PURE__ */ new Set();
      var ea = {};
      function fa(a, b) {
        ha(a, b);
        ha(a + "Capture", b);
      }
      function ha(a, b) {
        ea[a] = b;
        for (a = 0; a < b.length; a++) da.add(b[a]);
      }
      var ia = !("undefined" === typeof window || "undefined" === typeof window.document || "undefined" === typeof window.document.createElement);
      var ja = Object.prototype.hasOwnProperty;
      var ka = /^[:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD][:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD\-.0-9\u00B7\u0300-\u036F\u203F-\u2040]*$/;
      var la = {};
      var ma = {};
      function oa(a) {
        if (ja.call(ma, a)) return true;
        if (ja.call(la, a)) return false;
        if (ka.test(a)) return ma[a] = true;
        la[a] = true;
        return false;
      }
      function pa(a, b, c, d) {
        if (null !== c && 0 === c.type) return false;
        switch (typeof b) {
          case "function":
          case "symbol":
            return true;
          case "boolean":
            if (d) return false;
            if (null !== c) return !c.acceptsBooleans;
            a = a.toLowerCase().slice(0, 5);
            return "data-" !== a && "aria-" !== a;
          default:
            return false;
        }
      }
      function qa(a, b, c, d) {
        if (null === b || "undefined" === typeof b || pa(a, b, c, d)) return true;
        if (d) return false;
        if (null !== c) switch (c.type) {
          case 3:
            return !b;
          case 4:
            return false === b;
          case 5:
            return isNaN(b);
          case 6:
            return isNaN(b) || 1 > b;
        }
        return false;
      }
      function v(a, b, c, d, e, f, g) {
        this.acceptsBooleans = 2 === b || 3 === b || 4 === b;
        this.attributeName = d;
        this.attributeNamespace = e;
        this.mustUseProperty = c;
        this.propertyName = a;
        this.type = b;
        this.sanitizeURL = f;
        this.removeEmptyString = g;
      }
      var z = {};
      "children dangerouslySetInnerHTML defaultValue defaultChecked innerHTML suppressContentEditableWarning suppressHydrationWarning style".split(" ").forEach(function(a) {
        z[a] = new v(a, 0, false, a, null, false, false);
      });
      [["acceptCharset", "accept-charset"], ["className", "class"], ["htmlFor", "for"], ["httpEquiv", "http-equiv"]].forEach(function(a) {
        var b = a[0];
        z[b] = new v(b, 1, false, a[1], null, false, false);
      });
      ["contentEditable", "draggable", "spellCheck", "value"].forEach(function(a) {
        z[a] = new v(a, 2, false, a.toLowerCase(), null, false, false);
      });
      ["autoReverse", "externalResourcesRequired", "focusable", "preserveAlpha"].forEach(function(a) {
        z[a] = new v(a, 2, false, a, null, false, false);
      });
      "allowFullScreen async autoFocus autoPlay controls default defer disabled disablePictureInPicture disableRemotePlayback formNoValidate hidden loop noModule noValidate open playsInline readOnly required reversed scoped seamless itemScope".split(" ").forEach(function(a) {
        z[a] = new v(a, 3, false, a.toLowerCase(), null, false, false);
      });
      ["checked", "multiple", "muted", "selected"].forEach(function(a) {
        z[a] = new v(a, 3, true, a, null, false, false);
      });
      ["capture", "download"].forEach(function(a) {
        z[a] = new v(a, 4, false, a, null, false, false);
      });
      ["cols", "rows", "size", "span"].forEach(function(a) {
        z[a] = new v(a, 6, false, a, null, false, false);
      });
      ["rowSpan", "start"].forEach(function(a) {
        z[a] = new v(a, 5, false, a.toLowerCase(), null, false, false);
      });
      var ra = /[\-:]([a-z])/g;
      function sa(a) {
        return a[1].toUpperCase();
      }
      "accent-height alignment-baseline arabic-form baseline-shift cap-height clip-path clip-rule color-interpolation color-interpolation-filters color-profile color-rendering dominant-baseline enable-background fill-opacity fill-rule flood-color flood-opacity font-family font-size font-size-adjust font-stretch font-style font-variant font-weight glyph-name glyph-orientation-horizontal glyph-orientation-vertical horiz-adv-x horiz-origin-x image-rendering letter-spacing lighting-color marker-end marker-mid marker-start overline-position overline-thickness paint-order panose-1 pointer-events rendering-intent shape-rendering stop-color stop-opacity strikethrough-position strikethrough-thickness stroke-dasharray stroke-dashoffset stroke-linecap stroke-linejoin stroke-miterlimit stroke-opacity stroke-width text-anchor text-decoration text-rendering underline-position underline-thickness unicode-bidi unicode-range units-per-em v-alphabetic v-hanging v-ideographic v-mathematical vector-effect vert-adv-y vert-origin-x vert-origin-y word-spacing writing-mode xmlns:xlink x-height".split(" ").forEach(function(a) {
        var b = a.replace(
          ra,
          sa
        );
        z[b] = new v(b, 1, false, a, null, false, false);
      });
      "xlink:actuate xlink:arcrole xlink:role xlink:show xlink:title xlink:type".split(" ").forEach(function(a) {
        var b = a.replace(ra, sa);
        z[b] = new v(b, 1, false, a, "http://www.w3.org/1999/xlink", false, false);
      });
      ["xml:base", "xml:lang", "xml:space"].forEach(function(a) {
        var b = a.replace(ra, sa);
        z[b] = new v(b, 1, false, a, "http://www.w3.org/XML/1998/namespace", false, false);
      });
      ["tabIndex", "crossOrigin"].forEach(function(a) {
        z[a] = new v(a, 1, false, a.toLowerCase(), null, false, false);
      });
      z.xlinkHref = new v("xlinkHref", 1, false, "xlink:href", "http://www.w3.org/1999/xlink", true, false);
      ["src", "href", "action", "formAction"].forEach(function(a) {
        z[a] = new v(a, 1, false, a.toLowerCase(), null, true, true);
      });
      function ta(a, b, c, d) {
        var e = z.hasOwnProperty(b) ? z[b] : null;
        if (null !== e ? 0 !== e.type : d || !(2 < b.length) || "o" !== b[0] && "O" !== b[0] || "n" !== b[1] && "N" !== b[1]) qa(b, c, e, d) && (c = null), d || null === e ? oa(b) && (null === c ? a.removeAttribute(b) : a.setAttribute(b, "" + c)) : e.mustUseProperty ? a[e.propertyName] = null === c ? 3 === e.type ? false : "" : c : (b = e.attributeName, d = e.attributeNamespace, null === c ? a.removeAttribute(b) : (e = e.type, c = 3 === e || 4 === e && true === c ? "" : "" + c, d ? a.setAttributeNS(d, b, c) : a.setAttribute(b, c)));
      }
      var ua = aa.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED;
      var va = Symbol.for("react.element");
      var wa = Symbol.for("react.portal");
      var ya = Symbol.for("react.fragment");
      var za = Symbol.for("react.strict_mode");
      var Aa = Symbol.for("react.profiler");
      var Ba = Symbol.for("react.provider");
      var Ca = Symbol.for("react.context");
      var Da = Symbol.for("react.forward_ref");
      var Ea = Symbol.for("react.suspense");
      var Fa = Symbol.for("react.suspense_list");
      var Ga = Symbol.for("react.memo");
      var Ha = Symbol.for("react.lazy");
      Symbol.for("react.scope");
      Symbol.for("react.debug_trace_mode");
      var Ia = Symbol.for("react.offscreen");
      Symbol.for("react.legacy_hidden");
      Symbol.for("react.cache");
      Symbol.for("react.tracing_marker");
      var Ja = Symbol.iterator;
      function Ka(a) {
        if (null === a || "object" !== typeof a) return null;
        a = Ja && a[Ja] || a["@@iterator"];
        return "function" === typeof a ? a : null;
      }
      var A = Object.assign;
      var La;
      function Ma(a) {
        if (void 0 === La) try {
          throw Error();
        } catch (c) {
          var b = c.stack.trim().match(/\n( *(at )?)/);
          La = b && b[1] || "";
        }
        return "\n" + La + a;
      }
      var Na = false;
      function Oa(a, b) {
        if (!a || Na) return "";
        Na = true;
        var c = Error.prepareStackTrace;
        Error.prepareStackTrace = void 0;
        try {
          if (b) if (b = function() {
            throw Error();
          }, Object.defineProperty(b.prototype, "props", { set: function() {
            throw Error();
          } }), "object" === typeof Reflect && Reflect.construct) {
            try {
              Reflect.construct(b, []);
            } catch (l) {
              var d = l;
            }
            Reflect.construct(a, [], b);
          } else {
            try {
              b.call();
            } catch (l) {
              d = l;
            }
            a.call(b.prototype);
          }
          else {
            try {
              throw Error();
            } catch (l) {
              d = l;
            }
            a();
          }
        } catch (l) {
          if (l && d && "string" === typeof l.stack) {
            for (var e = l.stack.split("\n"), f = d.stack.split("\n"), g = e.length - 1, h = f.length - 1; 1 <= g && 0 <= h && e[g] !== f[h]; ) h--;
            for (; 1 <= g && 0 <= h; g--, h--) if (e[g] !== f[h]) {
              if (1 !== g || 1 !== h) {
                do
                  if (g--, h--, 0 > h || e[g] !== f[h]) {
                    var k = "\n" + e[g].replace(" at new ", " at ");
                    a.displayName && k.includes("<anonymous>") && (k = k.replace("<anonymous>", a.displayName));
                    return k;
                  }
                while (1 <= g && 0 <= h);
              }
              break;
            }
          }
        } finally {
          Na = false, Error.prepareStackTrace = c;
        }
        return (a = a ? a.displayName || a.name : "") ? Ma(a) : "";
      }
      function Pa(a) {
        switch (a.tag) {
          case 5:
            return Ma(a.type);
          case 16:
            return Ma("Lazy");
          case 13:
            return Ma("Suspense");
          case 19:
            return Ma("SuspenseList");
          case 0:
          case 2:
          case 15:
            return a = Oa(a.type, false), a;
          case 11:
            return a = Oa(a.type.render, false), a;
          case 1:
            return a = Oa(a.type, true), a;
          default:
            return "";
        }
      }
      function Qa(a) {
        if (null == a) return null;
        if ("function" === typeof a) return a.displayName || a.name || null;
        if ("string" === typeof a) return a;
        switch (a) {
          case ya:
            return "Fragment";
          case wa:
            return "Portal";
          case Aa:
            return "Profiler";
          case za:
            return "StrictMode";
          case Ea:
            return "Suspense";
          case Fa:
            return "SuspenseList";
        }
        if ("object" === typeof a) switch (a.$$typeof) {
          case Ca:
            return (a.displayName || "Context") + ".Consumer";
          case Ba:
            return (a._context.displayName || "Context") + ".Provider";
          case Da:
            var b = a.render;
            a = a.displayName;
            a || (a = b.displayName || b.name || "", a = "" !== a ? "ForwardRef(" + a + ")" : "ForwardRef");
            return a;
          case Ga:
            return b = a.displayName || null, null !== b ? b : Qa(a.type) || "Memo";
          case Ha:
            b = a._payload;
            a = a._init;
            try {
              return Qa(a(b));
            } catch (c) {
            }
        }
        return null;
      }
      function Ra(a) {
        var b = a.type;
        switch (a.tag) {
          case 24:
            return "Cache";
          case 9:
            return (b.displayName || "Context") + ".Consumer";
          case 10:
            return (b._context.displayName || "Context") + ".Provider";
          case 18:
            return "DehydratedFragment";
          case 11:
            return a = b.render, a = a.displayName || a.name || "", b.displayName || ("" !== a ? "ForwardRef(" + a + ")" : "ForwardRef");
          case 7:
            return "Fragment";
          case 5:
            return b;
          case 4:
            return "Portal";
          case 3:
            return "Root";
          case 6:
            return "Text";
          case 16:
            return Qa(b);
          case 8:
            return b === za ? "StrictMode" : "Mode";
          case 22:
            return "Offscreen";
          case 12:
            return "Profiler";
          case 21:
            return "Scope";
          case 13:
            return "Suspense";
          case 19:
            return "SuspenseList";
          case 25:
            return "TracingMarker";
          case 1:
          case 0:
          case 17:
          case 2:
          case 14:
          case 15:
            if ("function" === typeof b) return b.displayName || b.name || null;
            if ("string" === typeof b) return b;
        }
        return null;
      }
      function Sa(a) {
        switch (typeof a) {
          case "boolean":
          case "number":
          case "string":
          case "undefined":
            return a;
          case "object":
            return a;
          default:
            return "";
        }
      }
      function Ta(a) {
        var b = a.type;
        return (a = a.nodeName) && "input" === a.toLowerCase() && ("checkbox" === b || "radio" === b);
      }
      function Ua(a) {
        var b = Ta(a) ? "checked" : "value", c = Object.getOwnPropertyDescriptor(a.constructor.prototype, b), d = "" + a[b];
        if (!a.hasOwnProperty(b) && "undefined" !== typeof c && "function" === typeof c.get && "function" === typeof c.set) {
          var e = c.get, f = c.set;
          Object.defineProperty(a, b, { configurable: true, get: function() {
            return e.call(this);
          }, set: function(a2) {
            d = "" + a2;
            f.call(this, a2);
          } });
          Object.defineProperty(a, b, { enumerable: c.enumerable });
          return { getValue: function() {
            return d;
          }, setValue: function(a2) {
            d = "" + a2;
          }, stopTracking: function() {
            a._valueTracker = null;
            delete a[b];
          } };
        }
      }
      function Va(a) {
        a._valueTracker || (a._valueTracker = Ua(a));
      }
      function Wa(a) {
        if (!a) return false;
        var b = a._valueTracker;
        if (!b) return true;
        var c = b.getValue();
        var d = "";
        a && (d = Ta(a) ? a.checked ? "true" : "false" : a.value);
        a = d;
        return a !== c ? (b.setValue(a), true) : false;
      }
      function Xa(a) {
        a = a || ("undefined" !== typeof document ? document : void 0);
        if ("undefined" === typeof a) return null;
        try {
          return a.activeElement || a.body;
        } catch (b) {
          return a.body;
        }
      }
      function Ya(a, b) {
        var c = b.checked;
        return A({}, b, { defaultChecked: void 0, defaultValue: void 0, value: void 0, checked: null != c ? c : a._wrapperState.initialChecked });
      }
      function Za(a, b) {
        var c = null == b.defaultValue ? "" : b.defaultValue, d = null != b.checked ? b.checked : b.defaultChecked;
        c = Sa(null != b.value ? b.value : c);
        a._wrapperState = { initialChecked: d, initialValue: c, controlled: "checkbox" === b.type || "radio" === b.type ? null != b.checked : null != b.value };
      }
      function ab(a, b) {
        b = b.checked;
        null != b && ta(a, "checked", b, false);
      }
      function bb(a, b) {
        ab(a, b);
        var c = Sa(b.value), d = b.type;
        if (null != c) if ("number" === d) {
          if (0 === c && "" === a.value || a.value != c) a.value = "" + c;
        } else a.value !== "" + c && (a.value = "" + c);
        else if ("submit" === d || "reset" === d) {
          a.removeAttribute("value");
          return;
        }
        b.hasOwnProperty("value") ? cb(a, b.type, c) : b.hasOwnProperty("defaultValue") && cb(a, b.type, Sa(b.defaultValue));
        null == b.checked && null != b.defaultChecked && (a.defaultChecked = !!b.defaultChecked);
      }
      function db(a, b, c) {
        if (b.hasOwnProperty("value") || b.hasOwnProperty("defaultValue")) {
          var d = b.type;
          if (!("submit" !== d && "reset" !== d || void 0 !== b.value && null !== b.value)) return;
          b = "" + a._wrapperState.initialValue;
          c || b === a.value || (a.value = b);
          a.defaultValue = b;
        }
        c = a.name;
        "" !== c && (a.name = "");
        a.defaultChecked = !!a._wrapperState.initialChecked;
        "" !== c && (a.name = c);
      }
      function cb(a, b, c) {
        if ("number" !== b || Xa(a.ownerDocument) !== a) null == c ? a.defaultValue = "" + a._wrapperState.initialValue : a.defaultValue !== "" + c && (a.defaultValue = "" + c);
      }
      var eb = Array.isArray;
      function fb(a, b, c, d) {
        a = a.options;
        if (b) {
          b = {};
          for (var e = 0; e < c.length; e++) b["$" + c[e]] = true;
          for (c = 0; c < a.length; c++) e = b.hasOwnProperty("$" + a[c].value), a[c].selected !== e && (a[c].selected = e), e && d && (a[c].defaultSelected = true);
        } else {
          c = "" + Sa(c);
          b = null;
          for (e = 0; e < a.length; e++) {
            if (a[e].value === c) {
              a[e].selected = true;
              d && (a[e].defaultSelected = true);
              return;
            }
            null !== b || a[e].disabled || (b = a[e]);
          }
          null !== b && (b.selected = true);
        }
      }
      function gb(a, b) {
        if (null != b.dangerouslySetInnerHTML) throw Error(p(91));
        return A({}, b, { value: void 0, defaultValue: void 0, children: "" + a._wrapperState.initialValue });
      }
      function hb(a, b) {
        var c = b.value;
        if (null == c) {
          c = b.children;
          b = b.defaultValue;
          if (null != c) {
            if (null != b) throw Error(p(92));
            if (eb(c)) {
              if (1 < c.length) throw Error(p(93));
              c = c[0];
            }
            b = c;
          }
          null == b && (b = "");
          c = b;
        }
        a._wrapperState = { initialValue: Sa(c) };
      }
      function ib(a, b) {
        var c = Sa(b.value), d = Sa(b.defaultValue);
        null != c && (c = "" + c, c !== a.value && (a.value = c), null == b.defaultValue && a.defaultValue !== c && (a.defaultValue = c));
        null != d && (a.defaultValue = "" + d);
      }
      function jb(a) {
        var b = a.textContent;
        b === a._wrapperState.initialValue && "" !== b && null !== b && (a.value = b);
      }
      function kb(a) {
        switch (a) {
          case "svg":
            return "http://www.w3.org/2000/svg";
          case "math":
            return "http://www.w3.org/1998/Math/MathML";
          default:
            return "http://www.w3.org/1999/xhtml";
        }
      }
      function lb(a, b) {
        return null == a || "http://www.w3.org/1999/xhtml" === a ? kb(b) : "http://www.w3.org/2000/svg" === a && "foreignObject" === b ? "http://www.w3.org/1999/xhtml" : a;
      }
      var mb;
      var nb = (function(a) {
        return "undefined" !== typeof MSApp && MSApp.execUnsafeLocalFunction ? function(b, c, d, e) {
          MSApp.execUnsafeLocalFunction(function() {
            return a(b, c, d, e);
          });
        } : a;
      })(function(a, b) {
        if ("http://www.w3.org/2000/svg" !== a.namespaceURI || "innerHTML" in a) a.innerHTML = b;
        else {
          mb = mb || document.createElement("div");
          mb.innerHTML = "<svg>" + b.valueOf().toString() + "</svg>";
          for (b = mb.firstChild; a.firstChild; ) a.removeChild(a.firstChild);
          for (; b.firstChild; ) a.appendChild(b.firstChild);
        }
      });
      function ob(a, b) {
        if (b) {
          var c = a.firstChild;
          if (c && c === a.lastChild && 3 === c.nodeType) {
            c.nodeValue = b;
            return;
          }
        }
        a.textContent = b;
      }
      var pb = {
        animationIterationCount: true,
        aspectRatio: true,
        borderImageOutset: true,
        borderImageSlice: true,
        borderImageWidth: true,
        boxFlex: true,
        boxFlexGroup: true,
        boxOrdinalGroup: true,
        columnCount: true,
        columns: true,
        flex: true,
        flexGrow: true,
        flexPositive: true,
        flexShrink: true,
        flexNegative: true,
        flexOrder: true,
        gridArea: true,
        gridRow: true,
        gridRowEnd: true,
        gridRowSpan: true,
        gridRowStart: true,
        gridColumn: true,
        gridColumnEnd: true,
        gridColumnSpan: true,
        gridColumnStart: true,
        fontWeight: true,
        lineClamp: true,
        lineHeight: true,
        opacity: true,
        order: true,
        orphans: true,
        tabSize: true,
        widows: true,
        zIndex: true,
        zoom: true,
        fillOpacity: true,
        floodOpacity: true,
        stopOpacity: true,
        strokeDasharray: true,
        strokeDashoffset: true,
        strokeMiterlimit: true,
        strokeOpacity: true,
        strokeWidth: true
      };
      var qb = ["Webkit", "ms", "Moz", "O"];
      Object.keys(pb).forEach(function(a) {
        qb.forEach(function(b) {
          b = b + a.charAt(0).toUpperCase() + a.substring(1);
          pb[b] = pb[a];
        });
      });
      function rb(a, b, c) {
        return null == b || "boolean" === typeof b || "" === b ? "" : c || "number" !== typeof b || 0 === b || pb.hasOwnProperty(a) && pb[a] ? ("" + b).trim() : b + "px";
      }
      function sb(a, b) {
        a = a.style;
        for (var c in b) if (b.hasOwnProperty(c)) {
          var d = 0 === c.indexOf("--"), e = rb(c, b[c], d);
          "float" === c && (c = "cssFloat");
          d ? a.setProperty(c, e) : a[c] = e;
        }
      }
      var tb = A({ menuitem: true }, { area: true, base: true, br: true, col: true, embed: true, hr: true, img: true, input: true, keygen: true, link: true, meta: true, param: true, source: true, track: true, wbr: true });
      function ub(a, b) {
        if (b) {
          if (tb[a] && (null != b.children || null != b.dangerouslySetInnerHTML)) throw Error(p(137, a));
          if (null != b.dangerouslySetInnerHTML) {
            if (null != b.children) throw Error(p(60));
            if ("object" !== typeof b.dangerouslySetInnerHTML || !("__html" in b.dangerouslySetInnerHTML)) throw Error(p(61));
          }
          if (null != b.style && "object" !== typeof b.style) throw Error(p(62));
        }
      }
      function vb(a, b) {
        if (-1 === a.indexOf("-")) return "string" === typeof b.is;
        switch (a) {
          case "annotation-xml":
          case "color-profile":
          case "font-face":
          case "font-face-src":
          case "font-face-uri":
          case "font-face-format":
          case "font-face-name":
          case "missing-glyph":
            return false;
          default:
            return true;
        }
      }
      var wb = null;
      function xb(a) {
        a = a.target || a.srcElement || window;
        a.correspondingUseElement && (a = a.correspondingUseElement);
        return 3 === a.nodeType ? a.parentNode : a;
      }
      var yb = null;
      var zb = null;
      var Ab = null;
      function Bb(a) {
        if (a = Cb(a)) {
          if ("function" !== typeof yb) throw Error(p(280));
          var b = a.stateNode;
          b && (b = Db(b), yb(a.stateNode, a.type, b));
        }
      }
      function Eb(a) {
        zb ? Ab ? Ab.push(a) : Ab = [a] : zb = a;
      }
      function Fb() {
        if (zb) {
          var a = zb, b = Ab;
          Ab = zb = null;
          Bb(a);
          if (b) for (a = 0; a < b.length; a++) Bb(b[a]);
        }
      }
      function Gb(a, b) {
        return a(b);
      }
      function Hb() {
      }
      var Ib = false;
      function Jb(a, b, c) {
        if (Ib) return a(b, c);
        Ib = true;
        try {
          return Gb(a, b, c);
        } finally {
          if (Ib = false, null !== zb || null !== Ab) Hb(), Fb();
        }
      }
      function Kb(a, b) {
        var c = a.stateNode;
        if (null === c) return null;
        var d = Db(c);
        if (null === d) return null;
        c = d[b];
        a: switch (b) {
          case "onClick":
          case "onClickCapture":
          case "onDoubleClick":
          case "onDoubleClickCapture":
          case "onMouseDown":
          case "onMouseDownCapture":
          case "onMouseMove":
          case "onMouseMoveCapture":
          case "onMouseUp":
          case "onMouseUpCapture":
          case "onMouseEnter":
            (d = !d.disabled) || (a = a.type, d = !("button" === a || "input" === a || "select" === a || "textarea" === a));
            a = !d;
            break a;
          default:
            a = false;
        }
        if (a) return null;
        if (c && "function" !== typeof c) throw Error(p(231, b, typeof c));
        return c;
      }
      var Lb = false;
      if (ia) try {
        Mb = {};
        Object.defineProperty(Mb, "passive", { get: function() {
          Lb = true;
        } });
        window.addEventListener("test", Mb, Mb);
        window.removeEventListener("test", Mb, Mb);
      } catch (a) {
        Lb = false;
      }
      var Mb;
      function Nb(a, b, c, d, e, f, g, h, k) {
        var l = Array.prototype.slice.call(arguments, 3);
        try {
          b.apply(c, l);
        } catch (m) {
          this.onError(m);
        }
      }
      var Ob = false;
      var Pb = null;
      var Qb = false;
      var Rb = null;
      var Sb = { onError: function(a) {
        Ob = true;
        Pb = a;
      } };
      function Tb(a, b, c, d, e, f, g, h, k) {
        Ob = false;
        Pb = null;
        Nb.apply(Sb, arguments);
      }
      function Ub(a, b, c, d, e, f, g, h, k) {
        Tb.apply(this, arguments);
        if (Ob) {
          if (Ob) {
            var l = Pb;
            Ob = false;
            Pb = null;
          } else throw Error(p(198));
          Qb || (Qb = true, Rb = l);
        }
      }
      function Vb(a) {
        var b = a, c = a;
        if (a.alternate) for (; b.return; ) b = b.return;
        else {
          a = b;
          do
            b = a, 0 !== (b.flags & 4098) && (c = b.return), a = b.return;
          while (a);
        }
        return 3 === b.tag ? c : null;
      }
      function Wb(a) {
        if (13 === a.tag) {
          var b = a.memoizedState;
          null === b && (a = a.alternate, null !== a && (b = a.memoizedState));
          if (null !== b) return b.dehydrated;
        }
        return null;
      }
      function Xb(a) {
        if (Vb(a) !== a) throw Error(p(188));
      }
      function Yb(a) {
        var b = a.alternate;
        if (!b) {
          b = Vb(a);
          if (null === b) throw Error(p(188));
          return b !== a ? null : a;
        }
        for (var c = a, d = b; ; ) {
          var e = c.return;
          if (null === e) break;
          var f = e.alternate;
          if (null === f) {
            d = e.return;
            if (null !== d) {
              c = d;
              continue;
            }
            break;
          }
          if (e.child === f.child) {
            for (f = e.child; f; ) {
              if (f === c) return Xb(e), a;
              if (f === d) return Xb(e), b;
              f = f.sibling;
            }
            throw Error(p(188));
          }
          if (c.return !== d.return) c = e, d = f;
          else {
            for (var g = false, h = e.child; h; ) {
              if (h === c) {
                g = true;
                c = e;
                d = f;
                break;
              }
              if (h === d) {
                g = true;
                d = e;
                c = f;
                break;
              }
              h = h.sibling;
            }
            if (!g) {
              for (h = f.child; h; ) {
                if (h === c) {
                  g = true;
                  c = f;
                  d = e;
                  break;
                }
                if (h === d) {
                  g = true;
                  d = f;
                  c = e;
                  break;
                }
                h = h.sibling;
              }
              if (!g) throw Error(p(189));
            }
          }
          if (c.alternate !== d) throw Error(p(190));
        }
        if (3 !== c.tag) throw Error(p(188));
        return c.stateNode.current === c ? a : b;
      }
      function Zb(a) {
        a = Yb(a);
        return null !== a ? $b(a) : null;
      }
      function $b(a) {
        if (5 === a.tag || 6 === a.tag) return a;
        for (a = a.child; null !== a; ) {
          var b = $b(a);
          if (null !== b) return b;
          a = a.sibling;
        }
        return null;
      }
      var ac = ca.unstable_scheduleCallback;
      var bc = ca.unstable_cancelCallback;
      var cc = ca.unstable_shouldYield;
      var dc = ca.unstable_requestPaint;
      var B = ca.unstable_now;
      var ec = ca.unstable_getCurrentPriorityLevel;
      var fc = ca.unstable_ImmediatePriority;
      var gc = ca.unstable_UserBlockingPriority;
      var hc = ca.unstable_NormalPriority;
      var ic = ca.unstable_LowPriority;
      var jc = ca.unstable_IdlePriority;
      var kc = null;
      var lc = null;
      function mc(a) {
        if (lc && "function" === typeof lc.onCommitFiberRoot) try {
          lc.onCommitFiberRoot(kc, a, void 0, 128 === (a.current.flags & 128));
        } catch (b) {
        }
      }
      var oc = Math.clz32 ? Math.clz32 : nc;
      var pc = Math.log;
      var qc = Math.LN2;
      function nc(a) {
        a >>>= 0;
        return 0 === a ? 32 : 31 - (pc(a) / qc | 0) | 0;
      }
      var rc = 64;
      var sc = 4194304;
      function tc(a) {
        switch (a & -a) {
          case 1:
            return 1;
          case 2:
            return 2;
          case 4:
            return 4;
          case 8:
            return 8;
          case 16:
            return 16;
          case 32:
            return 32;
          case 64:
          case 128:
          case 256:
          case 512:
          case 1024:
          case 2048:
          case 4096:
          case 8192:
          case 16384:
          case 32768:
          case 65536:
          case 131072:
          case 262144:
          case 524288:
          case 1048576:
          case 2097152:
            return a & 4194240;
          case 4194304:
          case 8388608:
          case 16777216:
          case 33554432:
          case 67108864:
            return a & 130023424;
          case 134217728:
            return 134217728;
          case 268435456:
            return 268435456;
          case 536870912:
            return 536870912;
          case 1073741824:
            return 1073741824;
          default:
            return a;
        }
      }
      function uc(a, b) {
        var c = a.pendingLanes;
        if (0 === c) return 0;
        var d = 0, e = a.suspendedLanes, f = a.pingedLanes, g = c & 268435455;
        if (0 !== g) {
          var h = g & ~e;
          0 !== h ? d = tc(h) : (f &= g, 0 !== f && (d = tc(f)));
        } else g = c & ~e, 0 !== g ? d = tc(g) : 0 !== f && (d = tc(f));
        if (0 === d) return 0;
        if (0 !== b && b !== d && 0 === (b & e) && (e = d & -d, f = b & -b, e >= f || 16 === e && 0 !== (f & 4194240))) return b;
        0 !== (d & 4) && (d |= c & 16);
        b = a.entangledLanes;
        if (0 !== b) for (a = a.entanglements, b &= d; 0 < b; ) c = 31 - oc(b), e = 1 << c, d |= a[c], b &= ~e;
        return d;
      }
      function vc(a, b) {
        switch (a) {
          case 1:
          case 2:
          case 4:
            return b + 250;
          case 8:
          case 16:
          case 32:
          case 64:
          case 128:
          case 256:
          case 512:
          case 1024:
          case 2048:
          case 4096:
          case 8192:
          case 16384:
          case 32768:
          case 65536:
          case 131072:
          case 262144:
          case 524288:
          case 1048576:
          case 2097152:
            return b + 5e3;
          case 4194304:
          case 8388608:
          case 16777216:
          case 33554432:
          case 67108864:
            return -1;
          case 134217728:
          case 268435456:
          case 536870912:
          case 1073741824:
            return -1;
          default:
            return -1;
        }
      }
      function wc(a, b) {
        for (var c = a.suspendedLanes, d = a.pingedLanes, e = a.expirationTimes, f = a.pendingLanes; 0 < f; ) {
          var g = 31 - oc(f), h = 1 << g, k = e[g];
          if (-1 === k) {
            if (0 === (h & c) || 0 !== (h & d)) e[g] = vc(h, b);
          } else k <= b && (a.expiredLanes |= h);
          f &= ~h;
        }
      }
      function xc(a) {
        a = a.pendingLanes & -1073741825;
        return 0 !== a ? a : a & 1073741824 ? 1073741824 : 0;
      }
      function yc() {
        var a = rc;
        rc <<= 1;
        0 === (rc & 4194240) && (rc = 64);
        return a;
      }
      function zc(a) {
        for (var b = [], c = 0; 31 > c; c++) b.push(a);
        return b;
      }
      function Ac(a, b, c) {
        a.pendingLanes |= b;
        536870912 !== b && (a.suspendedLanes = 0, a.pingedLanes = 0);
        a = a.eventTimes;
        b = 31 - oc(b);
        a[b] = c;
      }
      function Bc(a, b) {
        var c = a.pendingLanes & ~b;
        a.pendingLanes = b;
        a.suspendedLanes = 0;
        a.pingedLanes = 0;
        a.expiredLanes &= b;
        a.mutableReadLanes &= b;
        a.entangledLanes &= b;
        b = a.entanglements;
        var d = a.eventTimes;
        for (a = a.expirationTimes; 0 < c; ) {
          var e = 31 - oc(c), f = 1 << e;
          b[e] = 0;
          d[e] = -1;
          a[e] = -1;
          c &= ~f;
        }
      }
      function Cc(a, b) {
        var c = a.entangledLanes |= b;
        for (a = a.entanglements; c; ) {
          var d = 31 - oc(c), e = 1 << d;
          e & b | a[d] & b && (a[d] |= b);
          c &= ~e;
        }
      }
      var C = 0;
      function Dc(a) {
        a &= -a;
        return 1 < a ? 4 < a ? 0 !== (a & 268435455) ? 16 : 536870912 : 4 : 1;
      }
      var Ec;
      var Fc;
      var Gc;
      var Hc;
      var Ic;
      var Jc = false;
      var Kc = [];
      var Lc = null;
      var Mc = null;
      var Nc = null;
      var Oc = /* @__PURE__ */ new Map();
      var Pc = /* @__PURE__ */ new Map();
      var Qc = [];
      var Rc = "mousedown mouseup touchcancel touchend touchstart auxclick dblclick pointercancel pointerdown pointerup dragend dragstart drop compositionend compositionstart keydown keypress keyup input textInput copy cut paste click change contextmenu reset submit".split(" ");
      function Sc(a, b) {
        switch (a) {
          case "focusin":
          case "focusout":
            Lc = null;
            break;
          case "dragenter":
          case "dragleave":
            Mc = null;
            break;
          case "mouseover":
          case "mouseout":
            Nc = null;
            break;
          case "pointerover":
          case "pointerout":
            Oc.delete(b.pointerId);
            break;
          case "gotpointercapture":
          case "lostpointercapture":
            Pc.delete(b.pointerId);
        }
      }
      function Tc(a, b, c, d, e, f) {
        if (null === a || a.nativeEvent !== f) return a = { blockedOn: b, domEventName: c, eventSystemFlags: d, nativeEvent: f, targetContainers: [e] }, null !== b && (b = Cb(b), null !== b && Fc(b)), a;
        a.eventSystemFlags |= d;
        b = a.targetContainers;
        null !== e && -1 === b.indexOf(e) && b.push(e);
        return a;
      }
      function Uc(a, b, c, d, e) {
        switch (b) {
          case "focusin":
            return Lc = Tc(Lc, a, b, c, d, e), true;
          case "dragenter":
            return Mc = Tc(Mc, a, b, c, d, e), true;
          case "mouseover":
            return Nc = Tc(Nc, a, b, c, d, e), true;
          case "pointerover":
            var f = e.pointerId;
            Oc.set(f, Tc(Oc.get(f) || null, a, b, c, d, e));
            return true;
          case "gotpointercapture":
            return f = e.pointerId, Pc.set(f, Tc(Pc.get(f) || null, a, b, c, d, e)), true;
        }
        return false;
      }
      function Vc(a) {
        var b = Wc(a.target);
        if (null !== b) {
          var c = Vb(b);
          if (null !== c) {
            if (b = c.tag, 13 === b) {
              if (b = Wb(c), null !== b) {
                a.blockedOn = b;
                Ic(a.priority, function() {
                  Gc(c);
                });
                return;
              }
            } else if (3 === b && c.stateNode.current.memoizedState.isDehydrated) {
              a.blockedOn = 3 === c.tag ? c.stateNode.containerInfo : null;
              return;
            }
          }
        }
        a.blockedOn = null;
      }
      function Xc(a) {
        if (null !== a.blockedOn) return false;
        for (var b = a.targetContainers; 0 < b.length; ) {
          var c = Yc(a.domEventName, a.eventSystemFlags, b[0], a.nativeEvent);
          if (null === c) {
            c = a.nativeEvent;
            var d = new c.constructor(c.type, c);
            wb = d;
            c.target.dispatchEvent(d);
            wb = null;
          } else return b = Cb(c), null !== b && Fc(b), a.blockedOn = c, false;
          b.shift();
        }
        return true;
      }
      function Zc(a, b, c) {
        Xc(a) && c.delete(b);
      }
      function $c() {
        Jc = false;
        null !== Lc && Xc(Lc) && (Lc = null);
        null !== Mc && Xc(Mc) && (Mc = null);
        null !== Nc && Xc(Nc) && (Nc = null);
        Oc.forEach(Zc);
        Pc.forEach(Zc);
      }
      function ad(a, b) {
        a.blockedOn === b && (a.blockedOn = null, Jc || (Jc = true, ca.unstable_scheduleCallback(ca.unstable_NormalPriority, $c)));
      }
      function bd(a) {
        function b(b2) {
          return ad(b2, a);
        }
        if (0 < Kc.length) {
          ad(Kc[0], a);
          for (var c = 1; c < Kc.length; c++) {
            var d = Kc[c];
            d.blockedOn === a && (d.blockedOn = null);
          }
        }
        null !== Lc && ad(Lc, a);
        null !== Mc && ad(Mc, a);
        null !== Nc && ad(Nc, a);
        Oc.forEach(b);
        Pc.forEach(b);
        for (c = 0; c < Qc.length; c++) d = Qc[c], d.blockedOn === a && (d.blockedOn = null);
        for (; 0 < Qc.length && (c = Qc[0], null === c.blockedOn); ) Vc(c), null === c.blockedOn && Qc.shift();
      }
      var cd = ua.ReactCurrentBatchConfig;
      var dd = true;
      function ed(a, b, c, d) {
        var e = C, f = cd.transition;
        cd.transition = null;
        try {
          C = 1, fd(a, b, c, d);
        } finally {
          C = e, cd.transition = f;
        }
      }
      function gd(a, b, c, d) {
        var e = C, f = cd.transition;
        cd.transition = null;
        try {
          C = 4, fd(a, b, c, d);
        } finally {
          C = e, cd.transition = f;
        }
      }
      function fd(a, b, c, d) {
        if (dd) {
          var e = Yc(a, b, c, d);
          if (null === e) hd(a, b, d, id, c), Sc(a, d);
          else if (Uc(e, a, b, c, d)) d.stopPropagation();
          else if (Sc(a, d), b & 4 && -1 < Rc.indexOf(a)) {
            for (; null !== e; ) {
              var f = Cb(e);
              null !== f && Ec(f);
              f = Yc(a, b, c, d);
              null === f && hd(a, b, d, id, c);
              if (f === e) break;
              e = f;
            }
            null !== e && d.stopPropagation();
          } else hd(a, b, d, null, c);
        }
      }
      var id = null;
      function Yc(a, b, c, d) {
        id = null;
        a = xb(d);
        a = Wc(a);
        if (null !== a) if (b = Vb(a), null === b) a = null;
        else if (c = b.tag, 13 === c) {
          a = Wb(b);
          if (null !== a) return a;
          a = null;
        } else if (3 === c) {
          if (b.stateNode.current.memoizedState.isDehydrated) return 3 === b.tag ? b.stateNode.containerInfo : null;
          a = null;
        } else b !== a && (a = null);
        id = a;
        return null;
      }
      function jd(a) {
        switch (a) {
          case "cancel":
          case "click":
          case "close":
          case "contextmenu":
          case "copy":
          case "cut":
          case "auxclick":
          case "dblclick":
          case "dragend":
          case "dragstart":
          case "drop":
          case "focusin":
          case "focusout":
          case "input":
          case "invalid":
          case "keydown":
          case "keypress":
          case "keyup":
          case "mousedown":
          case "mouseup":
          case "paste":
          case "pause":
          case "play":
          case "pointercancel":
          case "pointerdown":
          case "pointerup":
          case "ratechange":
          case "reset":
          case "resize":
          case "seeked":
          case "submit":
          case "touchcancel":
          case "touchend":
          case "touchstart":
          case "volumechange":
          case "change":
          case "selectionchange":
          case "textInput":
          case "compositionstart":
          case "compositionend":
          case "compositionupdate":
          case "beforeblur":
          case "afterblur":
          case "beforeinput":
          case "blur":
          case "fullscreenchange":
          case "focus":
          case "hashchange":
          case "popstate":
          case "select":
          case "selectstart":
            return 1;
          case "drag":
          case "dragenter":
          case "dragexit":
          case "dragleave":
          case "dragover":
          case "mousemove":
          case "mouseout":
          case "mouseover":
          case "pointermove":
          case "pointerout":
          case "pointerover":
          case "scroll":
          case "toggle":
          case "touchmove":
          case "wheel":
          case "mouseenter":
          case "mouseleave":
          case "pointerenter":
          case "pointerleave":
            return 4;
          case "message":
            switch (ec()) {
              case fc:
                return 1;
              case gc:
                return 4;
              case hc:
              case ic:
                return 16;
              case jc:
                return 536870912;
              default:
                return 16;
            }
          default:
            return 16;
        }
      }
      var kd = null;
      var ld = null;
      var md = null;
      function nd() {
        if (md) return md;
        var a, b = ld, c = b.length, d, e = "value" in kd ? kd.value : kd.textContent, f = e.length;
        for (a = 0; a < c && b[a] === e[a]; a++) ;
        var g = c - a;
        for (d = 1; d <= g && b[c - d] === e[f - d]; d++) ;
        return md = e.slice(a, 1 < d ? 1 - d : void 0);
      }
      function od(a) {
        var b = a.keyCode;
        "charCode" in a ? (a = a.charCode, 0 === a && 13 === b && (a = 13)) : a = b;
        10 === a && (a = 13);
        return 32 <= a || 13 === a ? a : 0;
      }
      function pd() {
        return true;
      }
      function qd() {
        return false;
      }
      function rd(a) {
        function b(b2, d, e, f, g) {
          this._reactName = b2;
          this._targetInst = e;
          this.type = d;
          this.nativeEvent = f;
          this.target = g;
          this.currentTarget = null;
          for (var c in a) a.hasOwnProperty(c) && (b2 = a[c], this[c] = b2 ? b2(f) : f[c]);
          this.isDefaultPrevented = (null != f.defaultPrevented ? f.defaultPrevented : false === f.returnValue) ? pd : qd;
          this.isPropagationStopped = qd;
          return this;
        }
        A(b.prototype, { preventDefault: function() {
          this.defaultPrevented = true;
          var a2 = this.nativeEvent;
          a2 && (a2.preventDefault ? a2.preventDefault() : "unknown" !== typeof a2.returnValue && (a2.returnValue = false), this.isDefaultPrevented = pd);
        }, stopPropagation: function() {
          var a2 = this.nativeEvent;
          a2 && (a2.stopPropagation ? a2.stopPropagation() : "unknown" !== typeof a2.cancelBubble && (a2.cancelBubble = true), this.isPropagationStopped = pd);
        }, persist: function() {
        }, isPersistent: pd });
        return b;
      }
      var sd = { eventPhase: 0, bubbles: 0, cancelable: 0, timeStamp: function(a) {
        return a.timeStamp || Date.now();
      }, defaultPrevented: 0, isTrusted: 0 };
      var td = rd(sd);
      var ud = A({}, sd, { view: 0, detail: 0 });
      var vd = rd(ud);
      var wd;
      var xd;
      var yd;
      var Ad = A({}, ud, { screenX: 0, screenY: 0, clientX: 0, clientY: 0, pageX: 0, pageY: 0, ctrlKey: 0, shiftKey: 0, altKey: 0, metaKey: 0, getModifierState: zd, button: 0, buttons: 0, relatedTarget: function(a) {
        return void 0 === a.relatedTarget ? a.fromElement === a.srcElement ? a.toElement : a.fromElement : a.relatedTarget;
      }, movementX: function(a) {
        if ("movementX" in a) return a.movementX;
        a !== yd && (yd && "mousemove" === a.type ? (wd = a.screenX - yd.screenX, xd = a.screenY - yd.screenY) : xd = wd = 0, yd = a);
        return wd;
      }, movementY: function(a) {
        return "movementY" in a ? a.movementY : xd;
      } });
      var Bd = rd(Ad);
      var Cd = A({}, Ad, { dataTransfer: 0 });
      var Dd = rd(Cd);
      var Ed = A({}, ud, { relatedTarget: 0 });
      var Fd = rd(Ed);
      var Gd = A({}, sd, { animationName: 0, elapsedTime: 0, pseudoElement: 0 });
      var Hd = rd(Gd);
      var Id = A({}, sd, { clipboardData: function(a) {
        return "clipboardData" in a ? a.clipboardData : window.clipboardData;
      } });
      var Jd = rd(Id);
      var Kd = A({}, sd, { data: 0 });
      var Ld = rd(Kd);
      var Md = {
        Esc: "Escape",
        Spacebar: " ",
        Left: "ArrowLeft",
        Up: "ArrowUp",
        Right: "ArrowRight",
        Down: "ArrowDown",
        Del: "Delete",
        Win: "OS",
        Menu: "ContextMenu",
        Apps: "ContextMenu",
        Scroll: "ScrollLock",
        MozPrintableKey: "Unidentified"
      };
      var Nd = {
        8: "Backspace",
        9: "Tab",
        12: "Clear",
        13: "Enter",
        16: "Shift",
        17: "Control",
        18: "Alt",
        19: "Pause",
        20: "CapsLock",
        27: "Escape",
        32: " ",
        33: "PageUp",
        34: "PageDown",
        35: "End",
        36: "Home",
        37: "ArrowLeft",
        38: "ArrowUp",
        39: "ArrowRight",
        40: "ArrowDown",
        45: "Insert",
        46: "Delete",
        112: "F1",
        113: "F2",
        114: "F3",
        115: "F4",
        116: "F5",
        117: "F6",
        118: "F7",
        119: "F8",
        120: "F9",
        121: "F10",
        122: "F11",
        123: "F12",
        144: "NumLock",
        145: "ScrollLock",
        224: "Meta"
      };
      var Od = { Alt: "altKey", Control: "ctrlKey", Meta: "metaKey", Shift: "shiftKey" };
      function Pd(a) {
        var b = this.nativeEvent;
        return b.getModifierState ? b.getModifierState(a) : (a = Od[a]) ? !!b[a] : false;
      }
      function zd() {
        return Pd;
      }
      var Qd = A({}, ud, { key: function(a) {
        if (a.key) {
          var b = Md[a.key] || a.key;
          if ("Unidentified" !== b) return b;
        }
        return "keypress" === a.type ? (a = od(a), 13 === a ? "Enter" : String.fromCharCode(a)) : "keydown" === a.type || "keyup" === a.type ? Nd[a.keyCode] || "Unidentified" : "";
      }, code: 0, location: 0, ctrlKey: 0, shiftKey: 0, altKey: 0, metaKey: 0, repeat: 0, locale: 0, getModifierState: zd, charCode: function(a) {
        return "keypress" === a.type ? od(a) : 0;
      }, keyCode: function(a) {
        return "keydown" === a.type || "keyup" === a.type ? a.keyCode : 0;
      }, which: function(a) {
        return "keypress" === a.type ? od(a) : "keydown" === a.type || "keyup" === a.type ? a.keyCode : 0;
      } });
      var Rd = rd(Qd);
      var Sd = A({}, Ad, { pointerId: 0, width: 0, height: 0, pressure: 0, tangentialPressure: 0, tiltX: 0, tiltY: 0, twist: 0, pointerType: 0, isPrimary: 0 });
      var Td = rd(Sd);
      var Ud = A({}, ud, { touches: 0, targetTouches: 0, changedTouches: 0, altKey: 0, metaKey: 0, ctrlKey: 0, shiftKey: 0, getModifierState: zd });
      var Vd = rd(Ud);
      var Wd = A({}, sd, { propertyName: 0, elapsedTime: 0, pseudoElement: 0 });
      var Xd = rd(Wd);
      var Yd = A({}, Ad, {
        deltaX: function(a) {
          return "deltaX" in a ? a.deltaX : "wheelDeltaX" in a ? -a.wheelDeltaX : 0;
        },
        deltaY: function(a) {
          return "deltaY" in a ? a.deltaY : "wheelDeltaY" in a ? -a.wheelDeltaY : "wheelDelta" in a ? -a.wheelDelta : 0;
        },
        deltaZ: 0,
        deltaMode: 0
      });
      var Zd = rd(Yd);
      var $d = [9, 13, 27, 32];
      var ae = ia && "CompositionEvent" in window;
      var be = null;
      ia && "documentMode" in document && (be = document.documentMode);
      var ce = ia && "TextEvent" in window && !be;
      var de = ia && (!ae || be && 8 < be && 11 >= be);
      var ee = String.fromCharCode(32);
      var fe = false;
      function ge(a, b) {
        switch (a) {
          case "keyup":
            return -1 !== $d.indexOf(b.keyCode);
          case "keydown":
            return 229 !== b.keyCode;
          case "keypress":
          case "mousedown":
          case "focusout":
            return true;
          default:
            return false;
        }
      }
      function he(a) {
        a = a.detail;
        return "object" === typeof a && "data" in a ? a.data : null;
      }
      var ie = false;
      function je(a, b) {
        switch (a) {
          case "compositionend":
            return he(b);
          case "keypress":
            if (32 !== b.which) return null;
            fe = true;
            return ee;
          case "textInput":
            return a = b.data, a === ee && fe ? null : a;
          default:
            return null;
        }
      }
      function ke(a, b) {
        if (ie) return "compositionend" === a || !ae && ge(a, b) ? (a = nd(), md = ld = kd = null, ie = false, a) : null;
        switch (a) {
          case "paste":
            return null;
          case "keypress":
            if (!(b.ctrlKey || b.altKey || b.metaKey) || b.ctrlKey && b.altKey) {
              if (b.char && 1 < b.char.length) return b.char;
              if (b.which) return String.fromCharCode(b.which);
            }
            return null;
          case "compositionend":
            return de && "ko" !== b.locale ? null : b.data;
          default:
            return null;
        }
      }
      var le = { color: true, date: true, datetime: true, "datetime-local": true, email: true, month: true, number: true, password: true, range: true, search: true, tel: true, text: true, time: true, url: true, week: true };
      function me(a) {
        var b = a && a.nodeName && a.nodeName.toLowerCase();
        return "input" === b ? !!le[a.type] : "textarea" === b ? true : false;
      }
      function ne(a, b, c, d) {
        Eb(d);
        b = oe(b, "onChange");
        0 < b.length && (c = new td("onChange", "change", null, c, d), a.push({ event: c, listeners: b }));
      }
      var pe = null;
      var qe = null;
      function re(a) {
        se(a, 0);
      }
      function te(a) {
        var b = ue(a);
        if (Wa(b)) return a;
      }
      function ve(a, b) {
        if ("change" === a) return b;
      }
      var we = false;
      if (ia) {
        if (ia) {
          ye = "oninput" in document;
          if (!ye) {
            ze = document.createElement("div");
            ze.setAttribute("oninput", "return;");
            ye = "function" === typeof ze.oninput;
          }
          xe = ye;
        } else xe = false;
        we = xe && (!document.documentMode || 9 < document.documentMode);
      }
      var xe;
      var ye;
      var ze;
      function Ae() {
        pe && (pe.detachEvent("onpropertychange", Be), qe = pe = null);
      }
      function Be(a) {
        if ("value" === a.propertyName && te(qe)) {
          var b = [];
          ne(b, qe, a, xb(a));
          Jb(re, b);
        }
      }
      function Ce(a, b, c) {
        "focusin" === a ? (Ae(), pe = b, qe = c, pe.attachEvent("onpropertychange", Be)) : "focusout" === a && Ae();
      }
      function De(a) {
        if ("selectionchange" === a || "keyup" === a || "keydown" === a) return te(qe);
      }
      function Ee(a, b) {
        if ("click" === a) return te(b);
      }
      function Fe(a, b) {
        if ("input" === a || "change" === a) return te(b);
      }
      function Ge(a, b) {
        return a === b && (0 !== a || 1 / a === 1 / b) || a !== a && b !== b;
      }
      var He = "function" === typeof Object.is ? Object.is : Ge;
      function Ie(a, b) {
        if (He(a, b)) return true;
        if ("object" !== typeof a || null === a || "object" !== typeof b || null === b) return false;
        var c = Object.keys(a), d = Object.keys(b);
        if (c.length !== d.length) return false;
        for (d = 0; d < c.length; d++) {
          var e = c[d];
          if (!ja.call(b, e) || !He(a[e], b[e])) return false;
        }
        return true;
      }
      function Je(a) {
        for (; a && a.firstChild; ) a = a.firstChild;
        return a;
      }
      function Ke(a, b) {
        var c = Je(a);
        a = 0;
        for (var d; c; ) {
          if (3 === c.nodeType) {
            d = a + c.textContent.length;
            if (a <= b && d >= b) return { node: c, offset: b - a };
            a = d;
          }
          a: {
            for (; c; ) {
              if (c.nextSibling) {
                c = c.nextSibling;
                break a;
              }
              c = c.parentNode;
            }
            c = void 0;
          }
          c = Je(c);
        }
      }
      function Le(a, b) {
        return a && b ? a === b ? true : a && 3 === a.nodeType ? false : b && 3 === b.nodeType ? Le(a, b.parentNode) : "contains" in a ? a.contains(b) : a.compareDocumentPosition ? !!(a.compareDocumentPosition(b) & 16) : false : false;
      }
      function Me() {
        for (var a = window, b = Xa(); b instanceof a.HTMLIFrameElement; ) {
          try {
            var c = "string" === typeof b.contentWindow.location.href;
          } catch (d) {
            c = false;
          }
          if (c) a = b.contentWindow;
          else break;
          b = Xa(a.document);
        }
        return b;
      }
      function Ne(a) {
        var b = a && a.nodeName && a.nodeName.toLowerCase();
        return b && ("input" === b && ("text" === a.type || "search" === a.type || "tel" === a.type || "url" === a.type || "password" === a.type) || "textarea" === b || "true" === a.contentEditable);
      }
      function Oe(a) {
        var b = Me(), c = a.focusedElem, d = a.selectionRange;
        if (b !== c && c && c.ownerDocument && Le(c.ownerDocument.documentElement, c)) {
          if (null !== d && Ne(c)) {
            if (b = d.start, a = d.end, void 0 === a && (a = b), "selectionStart" in c) c.selectionStart = b, c.selectionEnd = Math.min(a, c.value.length);
            else if (a = (b = c.ownerDocument || document) && b.defaultView || window, a.getSelection) {
              a = a.getSelection();
              var e = c.textContent.length, f = Math.min(d.start, e);
              d = void 0 === d.end ? f : Math.min(d.end, e);
              !a.extend && f > d && (e = d, d = f, f = e);
              e = Ke(c, f);
              var g = Ke(
                c,
                d
              );
              e && g && (1 !== a.rangeCount || a.anchorNode !== e.node || a.anchorOffset !== e.offset || a.focusNode !== g.node || a.focusOffset !== g.offset) && (b = b.createRange(), b.setStart(e.node, e.offset), a.removeAllRanges(), f > d ? (a.addRange(b), a.extend(g.node, g.offset)) : (b.setEnd(g.node, g.offset), a.addRange(b)));
            }
          }
          b = [];
          for (a = c; a = a.parentNode; ) 1 === a.nodeType && b.push({ element: a, left: a.scrollLeft, top: a.scrollTop });
          "function" === typeof c.focus && c.focus();
          for (c = 0; c < b.length; c++) a = b[c], a.element.scrollLeft = a.left, a.element.scrollTop = a.top;
        }
      }
      var Pe = ia && "documentMode" in document && 11 >= document.documentMode;
      var Qe = null;
      var Re = null;
      var Se = null;
      var Te = false;
      function Ue(a, b, c) {
        var d = c.window === c ? c.document : 9 === c.nodeType ? c : c.ownerDocument;
        Te || null == Qe || Qe !== Xa(d) || (d = Qe, "selectionStart" in d && Ne(d) ? d = { start: d.selectionStart, end: d.selectionEnd } : (d = (d.ownerDocument && d.ownerDocument.defaultView || window).getSelection(), d = { anchorNode: d.anchorNode, anchorOffset: d.anchorOffset, focusNode: d.focusNode, focusOffset: d.focusOffset }), Se && Ie(Se, d) || (Se = d, d = oe(Re, "onSelect"), 0 < d.length && (b = new td("onSelect", "select", null, b, c), a.push({ event: b, listeners: d }), b.target = Qe)));
      }
      function Ve(a, b) {
        var c = {};
        c[a.toLowerCase()] = b.toLowerCase();
        c["Webkit" + a] = "webkit" + b;
        c["Moz" + a] = "moz" + b;
        return c;
      }
      var We = { animationend: Ve("Animation", "AnimationEnd"), animationiteration: Ve("Animation", "AnimationIteration"), animationstart: Ve("Animation", "AnimationStart"), transitionend: Ve("Transition", "TransitionEnd") };
      var Xe = {};
      var Ye = {};
      ia && (Ye = document.createElement("div").style, "AnimationEvent" in window || (delete We.animationend.animation, delete We.animationiteration.animation, delete We.animationstart.animation), "TransitionEvent" in window || delete We.transitionend.transition);
      function Ze(a) {
        if (Xe[a]) return Xe[a];
        if (!We[a]) return a;
        var b = We[a], c;
        for (c in b) if (b.hasOwnProperty(c) && c in Ye) return Xe[a] = b[c];
        return a;
      }
      var $e = Ze("animationend");
      var af = Ze("animationiteration");
      var bf = Ze("animationstart");
      var cf = Ze("transitionend");
      var df = /* @__PURE__ */ new Map();
      var ef = "abort auxClick cancel canPlay canPlayThrough click close contextMenu copy cut drag dragEnd dragEnter dragExit dragLeave dragOver dragStart drop durationChange emptied encrypted ended error gotPointerCapture input invalid keyDown keyPress keyUp load loadedData loadedMetadata loadStart lostPointerCapture mouseDown mouseMove mouseOut mouseOver mouseUp paste pause play playing pointerCancel pointerDown pointerMove pointerOut pointerOver pointerUp progress rateChange reset resize seeked seeking stalled submit suspend timeUpdate touchCancel touchEnd touchStart volumeChange scroll toggle touchMove waiting wheel".split(" ");
      function ff(a, b) {
        df.set(a, b);
        fa(b, [a]);
      }
      for (gf = 0; gf < ef.length; gf++) {
        hf = ef[gf], jf = hf.toLowerCase(), kf = hf[0].toUpperCase() + hf.slice(1);
        ff(jf, "on" + kf);
      }
      var hf;
      var jf;
      var kf;
      var gf;
      ff($e, "onAnimationEnd");
      ff(af, "onAnimationIteration");
      ff(bf, "onAnimationStart");
      ff("dblclick", "onDoubleClick");
      ff("focusin", "onFocus");
      ff("focusout", "onBlur");
      ff(cf, "onTransitionEnd");
      ha("onMouseEnter", ["mouseout", "mouseover"]);
      ha("onMouseLeave", ["mouseout", "mouseover"]);
      ha("onPointerEnter", ["pointerout", "pointerover"]);
      ha("onPointerLeave", ["pointerout", "pointerover"]);
      fa("onChange", "change click focusin focusout input keydown keyup selectionchange".split(" "));
      fa("onSelect", "focusout contextmenu dragend focusin keydown keyup mousedown mouseup selectionchange".split(" "));
      fa("onBeforeInput", ["compositionend", "keypress", "textInput", "paste"]);
      fa("onCompositionEnd", "compositionend focusout keydown keypress keyup mousedown".split(" "));
      fa("onCompositionStart", "compositionstart focusout keydown keypress keyup mousedown".split(" "));
      fa("onCompositionUpdate", "compositionupdate focusout keydown keypress keyup mousedown".split(" "));
      var lf = "abort canplay canplaythrough durationchange emptied encrypted ended error loadeddata loadedmetadata loadstart pause play playing progress ratechange resize seeked seeking stalled suspend timeupdate volumechange waiting".split(" ");
      var mf = new Set("cancel close invalid load scroll toggle".split(" ").concat(lf));
      function nf(a, b, c) {
        var d = a.type || "unknown-event";
        a.currentTarget = c;
        Ub(d, b, void 0, a);
        a.currentTarget = null;
      }
      function se(a, b) {
        b = 0 !== (b & 4);
        for (var c = 0; c < a.length; c++) {
          var d = a[c], e = d.event;
          d = d.listeners;
          a: {
            var f = void 0;
            if (b) for (var g = d.length - 1; 0 <= g; g--) {
              var h = d[g], k = h.instance, l = h.currentTarget;
              h = h.listener;
              if (k !== f && e.isPropagationStopped()) break a;
              nf(e, h, l);
              f = k;
            }
            else for (g = 0; g < d.length; g++) {
              h = d[g];
              k = h.instance;
              l = h.currentTarget;
              h = h.listener;
              if (k !== f && e.isPropagationStopped()) break a;
              nf(e, h, l);
              f = k;
            }
          }
        }
        if (Qb) throw a = Rb, Qb = false, Rb = null, a;
      }
      function D(a, b) {
        var c = b[of];
        void 0 === c && (c = b[of] = /* @__PURE__ */ new Set());
        var d = a + "__bubble";
        c.has(d) || (pf(b, a, 2, false), c.add(d));
      }
      function qf(a, b, c) {
        var d = 0;
        b && (d |= 4);
        pf(c, a, d, b);
      }
      var rf = "_reactListening" + Math.random().toString(36).slice(2);
      function sf(a) {
        if (!a[rf]) {
          a[rf] = true;
          da.forEach(function(b2) {
            "selectionchange" !== b2 && (mf.has(b2) || qf(b2, false, a), qf(b2, true, a));
          });
          var b = 9 === a.nodeType ? a : a.ownerDocument;
          null === b || b[rf] || (b[rf] = true, qf("selectionchange", false, b));
        }
      }
      function pf(a, b, c, d) {
        switch (jd(b)) {
          case 1:
            var e = ed;
            break;
          case 4:
            e = gd;
            break;
          default:
            e = fd;
        }
        c = e.bind(null, b, c, a);
        e = void 0;
        !Lb || "touchstart" !== b && "touchmove" !== b && "wheel" !== b || (e = true);
        d ? void 0 !== e ? a.addEventListener(b, c, { capture: true, passive: e }) : a.addEventListener(b, c, true) : void 0 !== e ? a.addEventListener(b, c, { passive: e }) : a.addEventListener(b, c, false);
      }
      function hd(a, b, c, d, e) {
        var f = d;
        if (0 === (b & 1) && 0 === (b & 2) && null !== d) a: for (; ; ) {
          if (null === d) return;
          var g = d.tag;
          if (3 === g || 4 === g) {
            var h = d.stateNode.containerInfo;
            if (h === e || 8 === h.nodeType && h.parentNode === e) break;
            if (4 === g) for (g = d.return; null !== g; ) {
              var k = g.tag;
              if (3 === k || 4 === k) {
                if (k = g.stateNode.containerInfo, k === e || 8 === k.nodeType && k.parentNode === e) return;
              }
              g = g.return;
            }
            for (; null !== h; ) {
              g = Wc(h);
              if (null === g) return;
              k = g.tag;
              if (5 === k || 6 === k) {
                d = f = g;
                continue a;
              }
              h = h.parentNode;
            }
          }
          d = d.return;
        }
        Jb(function() {
          var d2 = f, e2 = xb(c), g2 = [];
          a: {
            var h2 = df.get(a);
            if (void 0 !== h2) {
              var k2 = td, n = a;
              switch (a) {
                case "keypress":
                  if (0 === od(c)) break a;
                case "keydown":
                case "keyup":
                  k2 = Rd;
                  break;
                case "focusin":
                  n = "focus";
                  k2 = Fd;
                  break;
                case "focusout":
                  n = "blur";
                  k2 = Fd;
                  break;
                case "beforeblur":
                case "afterblur":
                  k2 = Fd;
                  break;
                case "click":
                  if (2 === c.button) break a;
                case "auxclick":
                case "dblclick":
                case "mousedown":
                case "mousemove":
                case "mouseup":
                case "mouseout":
                case "mouseover":
                case "contextmenu":
                  k2 = Bd;
                  break;
                case "drag":
                case "dragend":
                case "dragenter":
                case "dragexit":
                case "dragleave":
                case "dragover":
                case "dragstart":
                case "drop":
                  k2 = Dd;
                  break;
                case "touchcancel":
                case "touchend":
                case "touchmove":
                case "touchstart":
                  k2 = Vd;
                  break;
                case $e:
                case af:
                case bf:
                  k2 = Hd;
                  break;
                case cf:
                  k2 = Xd;
                  break;
                case "scroll":
                  k2 = vd;
                  break;
                case "wheel":
                  k2 = Zd;
                  break;
                case "copy":
                case "cut":
                case "paste":
                  k2 = Jd;
                  break;
                case "gotpointercapture":
                case "lostpointercapture":
                case "pointercancel":
                case "pointerdown":
                case "pointermove":
                case "pointerout":
                case "pointerover":
                case "pointerup":
                  k2 = Td;
              }
              var t = 0 !== (b & 4), J = !t && "scroll" === a, x = t ? null !== h2 ? h2 + "Capture" : null : h2;
              t = [];
              for (var w = d2, u; null !== w; ) {
                u = w;
                var F = u.stateNode;
                5 === u.tag && null !== F && (u = F, null !== x && (F = Kb(w, x), null != F && t.push(tf(w, F, u))));
                if (J) break;
                w = w.return;
              }
              0 < t.length && (h2 = new k2(h2, n, null, c, e2), g2.push({ event: h2, listeners: t }));
            }
          }
          if (0 === (b & 7)) {
            a: {
              h2 = "mouseover" === a || "pointerover" === a;
              k2 = "mouseout" === a || "pointerout" === a;
              if (h2 && c !== wb && (n = c.relatedTarget || c.fromElement) && (Wc(n) || n[uf])) break a;
              if (k2 || h2) {
                h2 = e2.window === e2 ? e2 : (h2 = e2.ownerDocument) ? h2.defaultView || h2.parentWindow : window;
                if (k2) {
                  if (n = c.relatedTarget || c.toElement, k2 = d2, n = n ? Wc(n) : null, null !== n && (J = Vb(n), n !== J || 5 !== n.tag && 6 !== n.tag)) n = null;
                } else k2 = null, n = d2;
                if (k2 !== n) {
                  t = Bd;
                  F = "onMouseLeave";
                  x = "onMouseEnter";
                  w = "mouse";
                  if ("pointerout" === a || "pointerover" === a) t = Td, F = "onPointerLeave", x = "onPointerEnter", w = "pointer";
                  J = null == k2 ? h2 : ue(k2);
                  u = null == n ? h2 : ue(n);
                  h2 = new t(F, w + "leave", k2, c, e2);
                  h2.target = J;
                  h2.relatedTarget = u;
                  F = null;
                  Wc(e2) === d2 && (t = new t(x, w + "enter", n, c, e2), t.target = u, t.relatedTarget = J, F = t);
                  J = F;
                  if (k2 && n) b: {
                    t = k2;
                    x = n;
                    w = 0;
                    for (u = t; u; u = vf(u)) w++;
                    u = 0;
                    for (F = x; F; F = vf(F)) u++;
                    for (; 0 < w - u; ) t = vf(t), w--;
                    for (; 0 < u - w; ) x = vf(x), u--;
                    for (; w--; ) {
                      if (t === x || null !== x && t === x.alternate) break b;
                      t = vf(t);
                      x = vf(x);
                    }
                    t = null;
                  }
                  else t = null;
                  null !== k2 && wf(g2, h2, k2, t, false);
                  null !== n && null !== J && wf(g2, J, n, t, true);
                }
              }
            }
            a: {
              h2 = d2 ? ue(d2) : window;
              k2 = h2.nodeName && h2.nodeName.toLowerCase();
              if ("select" === k2 || "input" === k2 && "file" === h2.type) var na = ve;
              else if (me(h2)) if (we) na = Fe;
              else {
                na = De;
                var xa = Ce;
              }
              else (k2 = h2.nodeName) && "input" === k2.toLowerCase() && ("checkbox" === h2.type || "radio" === h2.type) && (na = Ee);
              if (na && (na = na(a, d2))) {
                ne(g2, na, c, e2);
                break a;
              }
              xa && xa(a, h2, d2);
              "focusout" === a && (xa = h2._wrapperState) && xa.controlled && "number" === h2.type && cb(h2, "number", h2.value);
            }
            xa = d2 ? ue(d2) : window;
            switch (a) {
              case "focusin":
                if (me(xa) || "true" === xa.contentEditable) Qe = xa, Re = d2, Se = null;
                break;
              case "focusout":
                Se = Re = Qe = null;
                break;
              case "mousedown":
                Te = true;
                break;
              case "contextmenu":
              case "mouseup":
              case "dragend":
                Te = false;
                Ue(g2, c, e2);
                break;
              case "selectionchange":
                if (Pe) break;
              case "keydown":
              case "keyup":
                Ue(g2, c, e2);
            }
            var $a;
            if (ae) b: {
              switch (a) {
                case "compositionstart":
                  var ba = "onCompositionStart";
                  break b;
                case "compositionend":
                  ba = "onCompositionEnd";
                  break b;
                case "compositionupdate":
                  ba = "onCompositionUpdate";
                  break b;
              }
              ba = void 0;
            }
            else ie ? ge(a, c) && (ba = "onCompositionEnd") : "keydown" === a && 229 === c.keyCode && (ba = "onCompositionStart");
            ba && (de && "ko" !== c.locale && (ie || "onCompositionStart" !== ba ? "onCompositionEnd" === ba && ie && ($a = nd()) : (kd = e2, ld = "value" in kd ? kd.value : kd.textContent, ie = true)), xa = oe(d2, ba), 0 < xa.length && (ba = new Ld(ba, a, null, c, e2), g2.push({ event: ba, listeners: xa }), $a ? ba.data = $a : ($a = he(c), null !== $a && (ba.data = $a))));
            if ($a = ce ? je(a, c) : ke(a, c)) d2 = oe(d2, "onBeforeInput"), 0 < d2.length && (e2 = new Ld("onBeforeInput", "beforeinput", null, c, e2), g2.push({ event: e2, listeners: d2 }), e2.data = $a);
          }
          se(g2, b);
        });
      }
      function tf(a, b, c) {
        return { instance: a, listener: b, currentTarget: c };
      }
      function oe(a, b) {
        for (var c = b + "Capture", d = []; null !== a; ) {
          var e = a, f = e.stateNode;
          5 === e.tag && null !== f && (e = f, f = Kb(a, c), null != f && d.unshift(tf(a, f, e)), f = Kb(a, b), null != f && d.push(tf(a, f, e)));
          a = a.return;
        }
        return d;
      }
      function vf(a) {
        if (null === a) return null;
        do
          a = a.return;
        while (a && 5 !== a.tag);
        return a ? a : null;
      }
      function wf(a, b, c, d, e) {
        for (var f = b._reactName, g = []; null !== c && c !== d; ) {
          var h = c, k = h.alternate, l = h.stateNode;
          if (null !== k && k === d) break;
          5 === h.tag && null !== l && (h = l, e ? (k = Kb(c, f), null != k && g.unshift(tf(c, k, h))) : e || (k = Kb(c, f), null != k && g.push(tf(c, k, h))));
          c = c.return;
        }
        0 !== g.length && a.push({ event: b, listeners: g });
      }
      var xf = /\r\n?/g;
      var yf = /\u0000|\uFFFD/g;
      function zf(a) {
        return ("string" === typeof a ? a : "" + a).replace(xf, "\n").replace(yf, "");
      }
      function Af(a, b, c) {
        b = zf(b);
        if (zf(a) !== b && c) throw Error(p(425));
      }
      function Bf() {
      }
      var Cf = null;
      var Df = null;
      function Ef(a, b) {
        return "textarea" === a || "noscript" === a || "string" === typeof b.children || "number" === typeof b.children || "object" === typeof b.dangerouslySetInnerHTML && null !== b.dangerouslySetInnerHTML && null != b.dangerouslySetInnerHTML.__html;
      }
      var Ff = "function" === typeof setTimeout ? setTimeout : void 0;
      var Gf = "function" === typeof clearTimeout ? clearTimeout : void 0;
      var Hf = "function" === typeof Promise ? Promise : void 0;
      var Jf = "function" === typeof queueMicrotask ? queueMicrotask : "undefined" !== typeof Hf ? function(a) {
        return Hf.resolve(null).then(a).catch(If);
      } : Ff;
      function If(a) {
        setTimeout(function() {
          throw a;
        });
      }
      function Kf(a, b) {
        var c = b, d = 0;
        do {
          var e = c.nextSibling;
          a.removeChild(c);
          if (e && 8 === e.nodeType) if (c = e.data, "/$" === c) {
            if (0 === d) {
              a.removeChild(e);
              bd(b);
              return;
            }
            d--;
          } else "$" !== c && "$?" !== c && "$!" !== c || d++;
          c = e;
        } while (c);
        bd(b);
      }
      function Lf(a) {
        for (; null != a; a = a.nextSibling) {
          var b = a.nodeType;
          if (1 === b || 3 === b) break;
          if (8 === b) {
            b = a.data;
            if ("$" === b || "$!" === b || "$?" === b) break;
            if ("/$" === b) return null;
          }
        }
        return a;
      }
      function Mf(a) {
        a = a.previousSibling;
        for (var b = 0; a; ) {
          if (8 === a.nodeType) {
            var c = a.data;
            if ("$" === c || "$!" === c || "$?" === c) {
              if (0 === b) return a;
              b--;
            } else "/$" === c && b++;
          }
          a = a.previousSibling;
        }
        return null;
      }
      var Nf = Math.random().toString(36).slice(2);
      var Of = "__reactFiber$" + Nf;
      var Pf = "__reactProps$" + Nf;
      var uf = "__reactContainer$" + Nf;
      var of = "__reactEvents$" + Nf;
      var Qf = "__reactListeners$" + Nf;
      var Rf = "__reactHandles$" + Nf;
      function Wc(a) {
        var b = a[Of];
        if (b) return b;
        for (var c = a.parentNode; c; ) {
          if (b = c[uf] || c[Of]) {
            c = b.alternate;
            if (null !== b.child || null !== c && null !== c.child) for (a = Mf(a); null !== a; ) {
              if (c = a[Of]) return c;
              a = Mf(a);
            }
            return b;
          }
          a = c;
          c = a.parentNode;
        }
        return null;
      }
      function Cb(a) {
        a = a[Of] || a[uf];
        return !a || 5 !== a.tag && 6 !== a.tag && 13 !== a.tag && 3 !== a.tag ? null : a;
      }
      function ue(a) {
        if (5 === a.tag || 6 === a.tag) return a.stateNode;
        throw Error(p(33));
      }
      function Db(a) {
        return a[Pf] || null;
      }
      var Sf = [];
      var Tf = -1;
      function Uf(a) {
        return { current: a };
      }
      function E(a) {
        0 > Tf || (a.current = Sf[Tf], Sf[Tf] = null, Tf--);
      }
      function G(a, b) {
        Tf++;
        Sf[Tf] = a.current;
        a.current = b;
      }
      var Vf = {};
      var H = Uf(Vf);
      var Wf = Uf(false);
      var Xf = Vf;
      function Yf(a, b) {
        var c = a.type.contextTypes;
        if (!c) return Vf;
        var d = a.stateNode;
        if (d && d.__reactInternalMemoizedUnmaskedChildContext === b) return d.__reactInternalMemoizedMaskedChildContext;
        var e = {}, f;
        for (f in c) e[f] = b[f];
        d && (a = a.stateNode, a.__reactInternalMemoizedUnmaskedChildContext = b, a.__reactInternalMemoizedMaskedChildContext = e);
        return e;
      }
      function Zf(a) {
        a = a.childContextTypes;
        return null !== a && void 0 !== a;
      }
      function $f() {
        E(Wf);
        E(H);
      }
      function ag(a, b, c) {
        if (H.current !== Vf) throw Error(p(168));
        G(H, b);
        G(Wf, c);
      }
      function bg(a, b, c) {
        var d = a.stateNode;
        b = b.childContextTypes;
        if ("function" !== typeof d.getChildContext) return c;
        d = d.getChildContext();
        for (var e in d) if (!(e in b)) throw Error(p(108, Ra(a) || "Unknown", e));
        return A({}, c, d);
      }
      function cg(a) {
        a = (a = a.stateNode) && a.__reactInternalMemoizedMergedChildContext || Vf;
        Xf = H.current;
        G(H, a);
        G(Wf, Wf.current);
        return true;
      }
      function dg(a, b, c) {
        var d = a.stateNode;
        if (!d) throw Error(p(169));
        c ? (a = bg(a, b, Xf), d.__reactInternalMemoizedMergedChildContext = a, E(Wf), E(H), G(H, a)) : E(Wf);
        G(Wf, c);
      }
      var eg = null;
      var fg = false;
      var gg = false;
      function hg(a) {
        null === eg ? eg = [a] : eg.push(a);
      }
      function ig(a) {
        fg = true;
        hg(a);
      }
      function jg() {
        if (!gg && null !== eg) {
          gg = true;
          var a = 0, b = C;
          try {
            var c = eg;
            for (C = 1; a < c.length; a++) {
              var d = c[a];
              do
                d = d(true);
              while (null !== d);
            }
            eg = null;
            fg = false;
          } catch (e) {
            throw null !== eg && (eg = eg.slice(a + 1)), ac(fc, jg), e;
          } finally {
            C = b, gg = false;
          }
        }
        return null;
      }
      var kg = [];
      var lg = 0;
      var mg = null;
      var ng = 0;
      var og = [];
      var pg = 0;
      var qg = null;
      var rg = 1;
      var sg = "";
      function tg(a, b) {
        kg[lg++] = ng;
        kg[lg++] = mg;
        mg = a;
        ng = b;
      }
      function ug(a, b, c) {
        og[pg++] = rg;
        og[pg++] = sg;
        og[pg++] = qg;
        qg = a;
        var d = rg;
        a = sg;
        var e = 32 - oc(d) - 1;
        d &= ~(1 << e);
        c += 1;
        var f = 32 - oc(b) + e;
        if (30 < f) {
          var g = e - e % 5;
          f = (d & (1 << g) - 1).toString(32);
          d >>= g;
          e -= g;
          rg = 1 << 32 - oc(b) + e | c << e | d;
          sg = f + a;
        } else rg = 1 << f | c << e | d, sg = a;
      }
      function vg(a) {
        null !== a.return && (tg(a, 1), ug(a, 1, 0));
      }
      function wg(a) {
        for (; a === mg; ) mg = kg[--lg], kg[lg] = null, ng = kg[--lg], kg[lg] = null;
        for (; a === qg; ) qg = og[--pg], og[pg] = null, sg = og[--pg], og[pg] = null, rg = og[--pg], og[pg] = null;
      }
      var xg = null;
      var yg = null;
      var I = false;
      var zg = null;
      function Ag(a, b) {
        var c = Bg(5, null, null, 0);
        c.elementType = "DELETED";
        c.stateNode = b;
        c.return = a;
        b = a.deletions;
        null === b ? (a.deletions = [c], a.flags |= 16) : b.push(c);
      }
      function Cg(a, b) {
        switch (a.tag) {
          case 5:
            var c = a.type;
            b = 1 !== b.nodeType || c.toLowerCase() !== b.nodeName.toLowerCase() ? null : b;
            return null !== b ? (a.stateNode = b, xg = a, yg = Lf(b.firstChild), true) : false;
          case 6:
            return b = "" === a.pendingProps || 3 !== b.nodeType ? null : b, null !== b ? (a.stateNode = b, xg = a, yg = null, true) : false;
          case 13:
            return b = 8 !== b.nodeType ? null : b, null !== b ? (c = null !== qg ? { id: rg, overflow: sg } : null, a.memoizedState = { dehydrated: b, treeContext: c, retryLane: 1073741824 }, c = Bg(18, null, null, 0), c.stateNode = b, c.return = a, a.child = c, xg = a, yg = null, true) : false;
          default:
            return false;
        }
      }
      function Dg(a) {
        return 0 !== (a.mode & 1) && 0 === (a.flags & 128);
      }
      function Eg(a) {
        if (I) {
          var b = yg;
          if (b) {
            var c = b;
            if (!Cg(a, b)) {
              if (Dg(a)) throw Error(p(418));
              b = Lf(c.nextSibling);
              var d = xg;
              b && Cg(a, b) ? Ag(d, c) : (a.flags = a.flags & -4097 | 2, I = false, xg = a);
            }
          } else {
            if (Dg(a)) throw Error(p(418));
            a.flags = a.flags & -4097 | 2;
            I = false;
            xg = a;
          }
        }
      }
      function Fg(a) {
        for (a = a.return; null !== a && 5 !== a.tag && 3 !== a.tag && 13 !== a.tag; ) a = a.return;
        xg = a;
      }
      function Gg(a) {
        if (a !== xg) return false;
        if (!I) return Fg(a), I = true, false;
        var b;
        (b = 3 !== a.tag) && !(b = 5 !== a.tag) && (b = a.type, b = "head" !== b && "body" !== b && !Ef(a.type, a.memoizedProps));
        if (b && (b = yg)) {
          if (Dg(a)) throw Hg(), Error(p(418));
          for (; b; ) Ag(a, b), b = Lf(b.nextSibling);
        }
        Fg(a);
        if (13 === a.tag) {
          a = a.memoizedState;
          a = null !== a ? a.dehydrated : null;
          if (!a) throw Error(p(317));
          a: {
            a = a.nextSibling;
            for (b = 0; a; ) {
              if (8 === a.nodeType) {
                var c = a.data;
                if ("/$" === c) {
                  if (0 === b) {
                    yg = Lf(a.nextSibling);
                    break a;
                  }
                  b--;
                } else "$" !== c && "$!" !== c && "$?" !== c || b++;
              }
              a = a.nextSibling;
            }
            yg = null;
          }
        } else yg = xg ? Lf(a.stateNode.nextSibling) : null;
        return true;
      }
      function Hg() {
        for (var a = yg; a; ) a = Lf(a.nextSibling);
      }
      function Ig() {
        yg = xg = null;
        I = false;
      }
      function Jg(a) {
        null === zg ? zg = [a] : zg.push(a);
      }
      var Kg = ua.ReactCurrentBatchConfig;
      function Lg(a, b, c) {
        a = c.ref;
        if (null !== a && "function" !== typeof a && "object" !== typeof a) {
          if (c._owner) {
            c = c._owner;
            if (c) {
              if (1 !== c.tag) throw Error(p(309));
              var d = c.stateNode;
            }
            if (!d) throw Error(p(147, a));
            var e = d, f = "" + a;
            if (null !== b && null !== b.ref && "function" === typeof b.ref && b.ref._stringRef === f) return b.ref;
            b = function(a2) {
              var b2 = e.refs;
              null === a2 ? delete b2[f] : b2[f] = a2;
            };
            b._stringRef = f;
            return b;
          }
          if ("string" !== typeof a) throw Error(p(284));
          if (!c._owner) throw Error(p(290, a));
        }
        return a;
      }
      function Mg(a, b) {
        a = Object.prototype.toString.call(b);
        throw Error(p(31, "[object Object]" === a ? "object with keys {" + Object.keys(b).join(", ") + "}" : a));
      }
      function Ng(a) {
        var b = a._init;
        return b(a._payload);
      }
      function Og(a) {
        function b(b2, c2) {
          if (a) {
            var d2 = b2.deletions;
            null === d2 ? (b2.deletions = [c2], b2.flags |= 16) : d2.push(c2);
          }
        }
        function c(c2, d2) {
          if (!a) return null;
          for (; null !== d2; ) b(c2, d2), d2 = d2.sibling;
          return null;
        }
        function d(a2, b2) {
          for (a2 = /* @__PURE__ */ new Map(); null !== b2; ) null !== b2.key ? a2.set(b2.key, b2) : a2.set(b2.index, b2), b2 = b2.sibling;
          return a2;
        }
        function e(a2, b2) {
          a2 = Pg(a2, b2);
          a2.index = 0;
          a2.sibling = null;
          return a2;
        }
        function f(b2, c2, d2) {
          b2.index = d2;
          if (!a) return b2.flags |= 1048576, c2;
          d2 = b2.alternate;
          if (null !== d2) return d2 = d2.index, d2 < c2 ? (b2.flags |= 2, c2) : d2;
          b2.flags |= 2;
          return c2;
        }
        function g(b2) {
          a && null === b2.alternate && (b2.flags |= 2);
          return b2;
        }
        function h(a2, b2, c2, d2) {
          if (null === b2 || 6 !== b2.tag) return b2 = Qg(c2, a2.mode, d2), b2.return = a2, b2;
          b2 = e(b2, c2);
          b2.return = a2;
          return b2;
        }
        function k(a2, b2, c2, d2) {
          var f2 = c2.type;
          if (f2 === ya) return m(a2, b2, c2.props.children, d2, c2.key);
          if (null !== b2 && (b2.elementType === f2 || "object" === typeof f2 && null !== f2 && f2.$$typeof === Ha && Ng(f2) === b2.type)) return d2 = e(b2, c2.props), d2.ref = Lg(a2, b2, c2), d2.return = a2, d2;
          d2 = Rg(c2.type, c2.key, c2.props, null, a2.mode, d2);
          d2.ref = Lg(a2, b2, c2);
          d2.return = a2;
          return d2;
        }
        function l(a2, b2, c2, d2) {
          if (null === b2 || 4 !== b2.tag || b2.stateNode.containerInfo !== c2.containerInfo || b2.stateNode.implementation !== c2.implementation) return b2 = Sg(c2, a2.mode, d2), b2.return = a2, b2;
          b2 = e(b2, c2.children || []);
          b2.return = a2;
          return b2;
        }
        function m(a2, b2, c2, d2, f2) {
          if (null === b2 || 7 !== b2.tag) return b2 = Tg(c2, a2.mode, d2, f2), b2.return = a2, b2;
          b2 = e(b2, c2);
          b2.return = a2;
          return b2;
        }
        function q(a2, b2, c2) {
          if ("string" === typeof b2 && "" !== b2 || "number" === typeof b2) return b2 = Qg("" + b2, a2.mode, c2), b2.return = a2, b2;
          if ("object" === typeof b2 && null !== b2) {
            switch (b2.$$typeof) {
              case va:
                return c2 = Rg(b2.type, b2.key, b2.props, null, a2.mode, c2), c2.ref = Lg(a2, null, b2), c2.return = a2, c2;
              case wa:
                return b2 = Sg(b2, a2.mode, c2), b2.return = a2, b2;
              case Ha:
                var d2 = b2._init;
                return q(a2, d2(b2._payload), c2);
            }
            if (eb(b2) || Ka(b2)) return b2 = Tg(b2, a2.mode, c2, null), b2.return = a2, b2;
            Mg(a2, b2);
          }
          return null;
        }
        function r(a2, b2, c2, d2) {
          var e2 = null !== b2 ? b2.key : null;
          if ("string" === typeof c2 && "" !== c2 || "number" === typeof c2) return null !== e2 ? null : h(a2, b2, "" + c2, d2);
          if ("object" === typeof c2 && null !== c2) {
            switch (c2.$$typeof) {
              case va:
                return c2.key === e2 ? k(a2, b2, c2, d2) : null;
              case wa:
                return c2.key === e2 ? l(a2, b2, c2, d2) : null;
              case Ha:
                return e2 = c2._init, r(
                  a2,
                  b2,
                  e2(c2._payload),
                  d2
                );
            }
            if (eb(c2) || Ka(c2)) return null !== e2 ? null : m(a2, b2, c2, d2, null);
            Mg(a2, c2);
          }
          return null;
        }
        function y(a2, b2, c2, d2, e2) {
          if ("string" === typeof d2 && "" !== d2 || "number" === typeof d2) return a2 = a2.get(c2) || null, h(b2, a2, "" + d2, e2);
          if ("object" === typeof d2 && null !== d2) {
            switch (d2.$$typeof) {
              case va:
                return a2 = a2.get(null === d2.key ? c2 : d2.key) || null, k(b2, a2, d2, e2);
              case wa:
                return a2 = a2.get(null === d2.key ? c2 : d2.key) || null, l(b2, a2, d2, e2);
              case Ha:
                var f2 = d2._init;
                return y(a2, b2, c2, f2(d2._payload), e2);
            }
            if (eb(d2) || Ka(d2)) return a2 = a2.get(c2) || null, m(b2, a2, d2, e2, null);
            Mg(b2, d2);
          }
          return null;
        }
        function n(e2, g2, h2, k2) {
          for (var l2 = null, m2 = null, u = g2, w = g2 = 0, x = null; null !== u && w < h2.length; w++) {
            u.index > w ? (x = u, u = null) : x = u.sibling;
            var n2 = r(e2, u, h2[w], k2);
            if (null === n2) {
              null === u && (u = x);
              break;
            }
            a && u && null === n2.alternate && b(e2, u);
            g2 = f(n2, g2, w);
            null === m2 ? l2 = n2 : m2.sibling = n2;
            m2 = n2;
            u = x;
          }
          if (w === h2.length) return c(e2, u), I && tg(e2, w), l2;
          if (null === u) {
            for (; w < h2.length; w++) u = q(e2, h2[w], k2), null !== u && (g2 = f(u, g2, w), null === m2 ? l2 = u : m2.sibling = u, m2 = u);
            I && tg(e2, w);
            return l2;
          }
          for (u = d(e2, u); w < h2.length; w++) x = y(u, e2, w, h2[w], k2), null !== x && (a && null !== x.alternate && u.delete(null === x.key ? w : x.key), g2 = f(x, g2, w), null === m2 ? l2 = x : m2.sibling = x, m2 = x);
          a && u.forEach(function(a2) {
            return b(e2, a2);
          });
          I && tg(e2, w);
          return l2;
        }
        function t(e2, g2, h2, k2) {
          var l2 = Ka(h2);
          if ("function" !== typeof l2) throw Error(p(150));
          h2 = l2.call(h2);
          if (null == h2) throw Error(p(151));
          for (var u = l2 = null, m2 = g2, w = g2 = 0, x = null, n2 = h2.next(); null !== m2 && !n2.done; w++, n2 = h2.next()) {
            m2.index > w ? (x = m2, m2 = null) : x = m2.sibling;
            var t2 = r(e2, m2, n2.value, k2);
            if (null === t2) {
              null === m2 && (m2 = x);
              break;
            }
            a && m2 && null === t2.alternate && b(e2, m2);
            g2 = f(t2, g2, w);
            null === u ? l2 = t2 : u.sibling = t2;
            u = t2;
            m2 = x;
          }
          if (n2.done) return c(
            e2,
            m2
          ), I && tg(e2, w), l2;
          if (null === m2) {
            for (; !n2.done; w++, n2 = h2.next()) n2 = q(e2, n2.value, k2), null !== n2 && (g2 = f(n2, g2, w), null === u ? l2 = n2 : u.sibling = n2, u = n2);
            I && tg(e2, w);
            return l2;
          }
          for (m2 = d(e2, m2); !n2.done; w++, n2 = h2.next()) n2 = y(m2, e2, w, n2.value, k2), null !== n2 && (a && null !== n2.alternate && m2.delete(null === n2.key ? w : n2.key), g2 = f(n2, g2, w), null === u ? l2 = n2 : u.sibling = n2, u = n2);
          a && m2.forEach(function(a2) {
            return b(e2, a2);
          });
          I && tg(e2, w);
          return l2;
        }
        function J(a2, d2, f2, h2) {
          "object" === typeof f2 && null !== f2 && f2.type === ya && null === f2.key && (f2 = f2.props.children);
          if ("object" === typeof f2 && null !== f2) {
            switch (f2.$$typeof) {
              case va:
                a: {
                  for (var k2 = f2.key, l2 = d2; null !== l2; ) {
                    if (l2.key === k2) {
                      k2 = f2.type;
                      if (k2 === ya) {
                        if (7 === l2.tag) {
                          c(a2, l2.sibling);
                          d2 = e(l2, f2.props.children);
                          d2.return = a2;
                          a2 = d2;
                          break a;
                        }
                      } else if (l2.elementType === k2 || "object" === typeof k2 && null !== k2 && k2.$$typeof === Ha && Ng(k2) === l2.type) {
                        c(a2, l2.sibling);
                        d2 = e(l2, f2.props);
                        d2.ref = Lg(a2, l2, f2);
                        d2.return = a2;
                        a2 = d2;
                        break a;
                      }
                      c(a2, l2);
                      break;
                    } else b(a2, l2);
                    l2 = l2.sibling;
                  }
                  f2.type === ya ? (d2 = Tg(f2.props.children, a2.mode, h2, f2.key), d2.return = a2, a2 = d2) : (h2 = Rg(f2.type, f2.key, f2.props, null, a2.mode, h2), h2.ref = Lg(a2, d2, f2), h2.return = a2, a2 = h2);
                }
                return g(a2);
              case wa:
                a: {
                  for (l2 = f2.key; null !== d2; ) {
                    if (d2.key === l2) if (4 === d2.tag && d2.stateNode.containerInfo === f2.containerInfo && d2.stateNode.implementation === f2.implementation) {
                      c(a2, d2.sibling);
                      d2 = e(d2, f2.children || []);
                      d2.return = a2;
                      a2 = d2;
                      break a;
                    } else {
                      c(a2, d2);
                      break;
                    }
                    else b(a2, d2);
                    d2 = d2.sibling;
                  }
                  d2 = Sg(f2, a2.mode, h2);
                  d2.return = a2;
                  a2 = d2;
                }
                return g(a2);
              case Ha:
                return l2 = f2._init, J(a2, d2, l2(f2._payload), h2);
            }
            if (eb(f2)) return n(a2, d2, f2, h2);
            if (Ka(f2)) return t(a2, d2, f2, h2);
            Mg(a2, f2);
          }
          return "string" === typeof f2 && "" !== f2 || "number" === typeof f2 ? (f2 = "" + f2, null !== d2 && 6 === d2.tag ? (c(a2, d2.sibling), d2 = e(d2, f2), d2.return = a2, a2 = d2) : (c(a2, d2), d2 = Qg(f2, a2.mode, h2), d2.return = a2, a2 = d2), g(a2)) : c(a2, d2);
        }
        return J;
      }
      var Ug = Og(true);
      var Vg = Og(false);
      var Wg = Uf(null);
      var Xg = null;
      var Yg = null;
      var Zg = null;
      function $g() {
        Zg = Yg = Xg = null;
      }
      function ah(a) {
        var b = Wg.current;
        E(Wg);
        a._currentValue = b;
      }
      function bh(a, b, c) {
        for (; null !== a; ) {
          var d = a.alternate;
          (a.childLanes & b) !== b ? (a.childLanes |= b, null !== d && (d.childLanes |= b)) : null !== d && (d.childLanes & b) !== b && (d.childLanes |= b);
          if (a === c) break;
          a = a.return;
        }
      }
      function ch(a, b) {
        Xg = a;
        Zg = Yg = null;
        a = a.dependencies;
        null !== a && null !== a.firstContext && (0 !== (a.lanes & b) && (dh = true), a.firstContext = null);
      }
      function eh(a) {
        var b = a._currentValue;
        if (Zg !== a) if (a = { context: a, memoizedValue: b, next: null }, null === Yg) {
          if (null === Xg) throw Error(p(308));
          Yg = a;
          Xg.dependencies = { lanes: 0, firstContext: a };
        } else Yg = Yg.next = a;
        return b;
      }
      var fh = null;
      function gh(a) {
        null === fh ? fh = [a] : fh.push(a);
      }
      function hh(a, b, c, d) {
        var e = b.interleaved;
        null === e ? (c.next = c, gh(b)) : (c.next = e.next, e.next = c);
        b.interleaved = c;
        return ih(a, d);
      }
      function ih(a, b) {
        a.lanes |= b;
        var c = a.alternate;
        null !== c && (c.lanes |= b);
        c = a;
        for (a = a.return; null !== a; ) a.childLanes |= b, c = a.alternate, null !== c && (c.childLanes |= b), c = a, a = a.return;
        return 3 === c.tag ? c.stateNode : null;
      }
      var jh = false;
      function kh(a) {
        a.updateQueue = { baseState: a.memoizedState, firstBaseUpdate: null, lastBaseUpdate: null, shared: { pending: null, interleaved: null, lanes: 0 }, effects: null };
      }
      function lh(a, b) {
        a = a.updateQueue;
        b.updateQueue === a && (b.updateQueue = { baseState: a.baseState, firstBaseUpdate: a.firstBaseUpdate, lastBaseUpdate: a.lastBaseUpdate, shared: a.shared, effects: a.effects });
      }
      function mh(a, b) {
        return { eventTime: a, lane: b, tag: 0, payload: null, callback: null, next: null };
      }
      function nh(a, b, c) {
        var d = a.updateQueue;
        if (null === d) return null;
        d = d.shared;
        if (0 !== (K & 2)) {
          var e = d.pending;
          null === e ? b.next = b : (b.next = e.next, e.next = b);
          d.pending = b;
          return ih(a, c);
        }
        e = d.interleaved;
        null === e ? (b.next = b, gh(d)) : (b.next = e.next, e.next = b);
        d.interleaved = b;
        return ih(a, c);
      }
      function oh(a, b, c) {
        b = b.updateQueue;
        if (null !== b && (b = b.shared, 0 !== (c & 4194240))) {
          var d = b.lanes;
          d &= a.pendingLanes;
          c |= d;
          b.lanes = c;
          Cc(a, c);
        }
      }
      function ph(a, b) {
        var c = a.updateQueue, d = a.alternate;
        if (null !== d && (d = d.updateQueue, c === d)) {
          var e = null, f = null;
          c = c.firstBaseUpdate;
          if (null !== c) {
            do {
              var g = { eventTime: c.eventTime, lane: c.lane, tag: c.tag, payload: c.payload, callback: c.callback, next: null };
              null === f ? e = f = g : f = f.next = g;
              c = c.next;
            } while (null !== c);
            null === f ? e = f = b : f = f.next = b;
          } else e = f = b;
          c = { baseState: d.baseState, firstBaseUpdate: e, lastBaseUpdate: f, shared: d.shared, effects: d.effects };
          a.updateQueue = c;
          return;
        }
        a = c.lastBaseUpdate;
        null === a ? c.firstBaseUpdate = b : a.next = b;
        c.lastBaseUpdate = b;
      }
      function qh(a, b, c, d) {
        var e = a.updateQueue;
        jh = false;
        var f = e.firstBaseUpdate, g = e.lastBaseUpdate, h = e.shared.pending;
        if (null !== h) {
          e.shared.pending = null;
          var k = h, l = k.next;
          k.next = null;
          null === g ? f = l : g.next = l;
          g = k;
          var m = a.alternate;
          null !== m && (m = m.updateQueue, h = m.lastBaseUpdate, h !== g && (null === h ? m.firstBaseUpdate = l : h.next = l, m.lastBaseUpdate = k));
        }
        if (null !== f) {
          var q = e.baseState;
          g = 0;
          m = l = k = null;
          h = f;
          do {
            var r = h.lane, y = h.eventTime;
            if ((d & r) === r) {
              null !== m && (m = m.next = {
                eventTime: y,
                lane: 0,
                tag: h.tag,
                payload: h.payload,
                callback: h.callback,
                next: null
              });
              a: {
                var n = a, t = h;
                r = b;
                y = c;
                switch (t.tag) {
                  case 1:
                    n = t.payload;
                    if ("function" === typeof n) {
                      q = n.call(y, q, r);
                      break a;
                    }
                    q = n;
                    break a;
                  case 3:
                    n.flags = n.flags & -65537 | 128;
                  case 0:
                    n = t.payload;
                    r = "function" === typeof n ? n.call(y, q, r) : n;
                    if (null === r || void 0 === r) break a;
                    q = A({}, q, r);
                    break a;
                  case 2:
                    jh = true;
                }
              }
              null !== h.callback && 0 !== h.lane && (a.flags |= 64, r = e.effects, null === r ? e.effects = [h] : r.push(h));
            } else y = { eventTime: y, lane: r, tag: h.tag, payload: h.payload, callback: h.callback, next: null }, null === m ? (l = m = y, k = q) : m = m.next = y, g |= r;
            h = h.next;
            if (null === h) if (h = e.shared.pending, null === h) break;
            else r = h, h = r.next, r.next = null, e.lastBaseUpdate = r, e.shared.pending = null;
          } while (1);
          null === m && (k = q);
          e.baseState = k;
          e.firstBaseUpdate = l;
          e.lastBaseUpdate = m;
          b = e.shared.interleaved;
          if (null !== b) {
            e = b;
            do
              g |= e.lane, e = e.next;
            while (e !== b);
          } else null === f && (e.shared.lanes = 0);
          rh |= g;
          a.lanes = g;
          a.memoizedState = q;
        }
      }
      function sh(a, b, c) {
        a = b.effects;
        b.effects = null;
        if (null !== a) for (b = 0; b < a.length; b++) {
          var d = a[b], e = d.callback;
          if (null !== e) {
            d.callback = null;
            d = c;
            if ("function" !== typeof e) throw Error(p(191, e));
            e.call(d);
          }
        }
      }
      var th = {};
      var uh = Uf(th);
      var vh = Uf(th);
      var wh = Uf(th);
      function xh(a) {
        if (a === th) throw Error(p(174));
        return a;
      }
      function yh(a, b) {
        G(wh, b);
        G(vh, a);
        G(uh, th);
        a = b.nodeType;
        switch (a) {
          case 9:
          case 11:
            b = (b = b.documentElement) ? b.namespaceURI : lb(null, "");
            break;
          default:
            a = 8 === a ? b.parentNode : b, b = a.namespaceURI || null, a = a.tagName, b = lb(b, a);
        }
        E(uh);
        G(uh, b);
      }
      function zh() {
        E(uh);
        E(vh);
        E(wh);
      }
      function Ah(a) {
        xh(wh.current);
        var b = xh(uh.current);
        var c = lb(b, a.type);
        b !== c && (G(vh, a), G(uh, c));
      }
      function Bh(a) {
        vh.current === a && (E(uh), E(vh));
      }
      var L = Uf(0);
      function Ch(a) {
        for (var b = a; null !== b; ) {
          if (13 === b.tag) {
            var c = b.memoizedState;
            if (null !== c && (c = c.dehydrated, null === c || "$?" === c.data || "$!" === c.data)) return b;
          } else if (19 === b.tag && void 0 !== b.memoizedProps.revealOrder) {
            if (0 !== (b.flags & 128)) return b;
          } else if (null !== b.child) {
            b.child.return = b;
            b = b.child;
            continue;
          }
          if (b === a) break;
          for (; null === b.sibling; ) {
            if (null === b.return || b.return === a) return null;
            b = b.return;
          }
          b.sibling.return = b.return;
          b = b.sibling;
        }
        return null;
      }
      var Dh = [];
      function Eh() {
        for (var a = 0; a < Dh.length; a++) Dh[a]._workInProgressVersionPrimary = null;
        Dh.length = 0;
      }
      var Fh = ua.ReactCurrentDispatcher;
      var Gh = ua.ReactCurrentBatchConfig;
      var Hh = 0;
      var M = null;
      var N = null;
      var O = null;
      var Ih = false;
      var Jh = false;
      var Kh = 0;
      var Lh = 0;
      function P() {
        throw Error(p(321));
      }
      function Mh(a, b) {
        if (null === b) return false;
        for (var c = 0; c < b.length && c < a.length; c++) if (!He(a[c], b[c])) return false;
        return true;
      }
      function Nh(a, b, c, d, e, f) {
        Hh = f;
        M = b;
        b.memoizedState = null;
        b.updateQueue = null;
        b.lanes = 0;
        Fh.current = null === a || null === a.memoizedState ? Oh : Ph;
        a = c(d, e);
        if (Jh) {
          f = 0;
          do {
            Jh = false;
            Kh = 0;
            if (25 <= f) throw Error(p(301));
            f += 1;
            O = N = null;
            b.updateQueue = null;
            Fh.current = Qh;
            a = c(d, e);
          } while (Jh);
        }
        Fh.current = Rh;
        b = null !== N && null !== N.next;
        Hh = 0;
        O = N = M = null;
        Ih = false;
        if (b) throw Error(p(300));
        return a;
      }
      function Sh() {
        var a = 0 !== Kh;
        Kh = 0;
        return a;
      }
      function Th() {
        var a = { memoizedState: null, baseState: null, baseQueue: null, queue: null, next: null };
        null === O ? M.memoizedState = O = a : O = O.next = a;
        return O;
      }
      function Uh() {
        if (null === N) {
          var a = M.alternate;
          a = null !== a ? a.memoizedState : null;
        } else a = N.next;
        var b = null === O ? M.memoizedState : O.next;
        if (null !== b) O = b, N = a;
        else {
          if (null === a) throw Error(p(310));
          N = a;
          a = { memoizedState: N.memoizedState, baseState: N.baseState, baseQueue: N.baseQueue, queue: N.queue, next: null };
          null === O ? M.memoizedState = O = a : O = O.next = a;
        }
        return O;
      }
      function Vh(a, b) {
        return "function" === typeof b ? b(a) : b;
      }
      function Wh(a) {
        var b = Uh(), c = b.queue;
        if (null === c) throw Error(p(311));
        c.lastRenderedReducer = a;
        var d = N, e = d.baseQueue, f = c.pending;
        if (null !== f) {
          if (null !== e) {
            var g = e.next;
            e.next = f.next;
            f.next = g;
          }
          d.baseQueue = e = f;
          c.pending = null;
        }
        if (null !== e) {
          f = e.next;
          d = d.baseState;
          var h = g = null, k = null, l = f;
          do {
            var m = l.lane;
            if ((Hh & m) === m) null !== k && (k = k.next = { lane: 0, action: l.action, hasEagerState: l.hasEagerState, eagerState: l.eagerState, next: null }), d = l.hasEagerState ? l.eagerState : a(d, l.action);
            else {
              var q = {
                lane: m,
                action: l.action,
                hasEagerState: l.hasEagerState,
                eagerState: l.eagerState,
                next: null
              };
              null === k ? (h = k = q, g = d) : k = k.next = q;
              M.lanes |= m;
              rh |= m;
            }
            l = l.next;
          } while (null !== l && l !== f);
          null === k ? g = d : k.next = h;
          He(d, b.memoizedState) || (dh = true);
          b.memoizedState = d;
          b.baseState = g;
          b.baseQueue = k;
          c.lastRenderedState = d;
        }
        a = c.interleaved;
        if (null !== a) {
          e = a;
          do
            f = e.lane, M.lanes |= f, rh |= f, e = e.next;
          while (e !== a);
        } else null === e && (c.lanes = 0);
        return [b.memoizedState, c.dispatch];
      }
      function Xh(a) {
        var b = Uh(), c = b.queue;
        if (null === c) throw Error(p(311));
        c.lastRenderedReducer = a;
        var d = c.dispatch, e = c.pending, f = b.memoizedState;
        if (null !== e) {
          c.pending = null;
          var g = e = e.next;
          do
            f = a(f, g.action), g = g.next;
          while (g !== e);
          He(f, b.memoizedState) || (dh = true);
          b.memoizedState = f;
          null === b.baseQueue && (b.baseState = f);
          c.lastRenderedState = f;
        }
        return [f, d];
      }
      function Yh() {
      }
      function Zh(a, b) {
        var c = M, d = Uh(), e = b(), f = !He(d.memoizedState, e);
        f && (d.memoizedState = e, dh = true);
        d = d.queue;
        $h(ai.bind(null, c, d, a), [a]);
        if (d.getSnapshot !== b || f || null !== O && O.memoizedState.tag & 1) {
          c.flags |= 2048;
          bi(9, ci.bind(null, c, d, e, b), void 0, null);
          if (null === Q) throw Error(p(349));
          0 !== (Hh & 30) || di(c, b, e);
        }
        return e;
      }
      function di(a, b, c) {
        a.flags |= 16384;
        a = { getSnapshot: b, value: c };
        b = M.updateQueue;
        null === b ? (b = { lastEffect: null, stores: null }, M.updateQueue = b, b.stores = [a]) : (c = b.stores, null === c ? b.stores = [a] : c.push(a));
      }
      function ci(a, b, c, d) {
        b.value = c;
        b.getSnapshot = d;
        ei(b) && fi(a);
      }
      function ai(a, b, c) {
        return c(function() {
          ei(b) && fi(a);
        });
      }
      function ei(a) {
        var b = a.getSnapshot;
        a = a.value;
        try {
          var c = b();
          return !He(a, c);
        } catch (d) {
          return true;
        }
      }
      function fi(a) {
        var b = ih(a, 1);
        null !== b && gi(b, a, 1, -1);
      }
      function hi(a) {
        var b = Th();
        "function" === typeof a && (a = a());
        b.memoizedState = b.baseState = a;
        a = { pending: null, interleaved: null, lanes: 0, dispatch: null, lastRenderedReducer: Vh, lastRenderedState: a };
        b.queue = a;
        a = a.dispatch = ii.bind(null, M, a);
        return [b.memoizedState, a];
      }
      function bi(a, b, c, d) {
        a = { tag: a, create: b, destroy: c, deps: d, next: null };
        b = M.updateQueue;
        null === b ? (b = { lastEffect: null, stores: null }, M.updateQueue = b, b.lastEffect = a.next = a) : (c = b.lastEffect, null === c ? b.lastEffect = a.next = a : (d = c.next, c.next = a, a.next = d, b.lastEffect = a));
        return a;
      }
      function ji() {
        return Uh().memoizedState;
      }
      function ki(a, b, c, d) {
        var e = Th();
        M.flags |= a;
        e.memoizedState = bi(1 | b, c, void 0, void 0 === d ? null : d);
      }
      function li(a, b, c, d) {
        var e = Uh();
        d = void 0 === d ? null : d;
        var f = void 0;
        if (null !== N) {
          var g = N.memoizedState;
          f = g.destroy;
          if (null !== d && Mh(d, g.deps)) {
            e.memoizedState = bi(b, c, f, d);
            return;
          }
        }
        M.flags |= a;
        e.memoizedState = bi(1 | b, c, f, d);
      }
      function mi(a, b) {
        return ki(8390656, 8, a, b);
      }
      function $h(a, b) {
        return li(2048, 8, a, b);
      }
      function ni(a, b) {
        return li(4, 2, a, b);
      }
      function oi(a, b) {
        return li(4, 4, a, b);
      }
      function pi(a, b) {
        if ("function" === typeof b) return a = a(), b(a), function() {
          b(null);
        };
        if (null !== b && void 0 !== b) return a = a(), b.current = a, function() {
          b.current = null;
        };
      }
      function qi(a, b, c) {
        c = null !== c && void 0 !== c ? c.concat([a]) : null;
        return li(4, 4, pi.bind(null, b, a), c);
      }
      function ri() {
      }
      function si(a, b) {
        var c = Uh();
        b = void 0 === b ? null : b;
        var d = c.memoizedState;
        if (null !== d && null !== b && Mh(b, d[1])) return d[0];
        c.memoizedState = [a, b];
        return a;
      }
      function ti(a, b) {
        var c = Uh();
        b = void 0 === b ? null : b;
        var d = c.memoizedState;
        if (null !== d && null !== b && Mh(b, d[1])) return d[0];
        a = a();
        c.memoizedState = [a, b];
        return a;
      }
      function ui(a, b, c) {
        if (0 === (Hh & 21)) return a.baseState && (a.baseState = false, dh = true), a.memoizedState = c;
        He(c, b) || (c = yc(), M.lanes |= c, rh |= c, a.baseState = true);
        return b;
      }
      function vi(a, b) {
        var c = C;
        C = 0 !== c && 4 > c ? c : 4;
        a(true);
        var d = Gh.transition;
        Gh.transition = {};
        try {
          a(false), b();
        } finally {
          C = c, Gh.transition = d;
        }
      }
      function wi() {
        return Uh().memoizedState;
      }
      function xi(a, b, c) {
        var d = yi(a);
        c = { lane: d, action: c, hasEagerState: false, eagerState: null, next: null };
        if (zi(a)) Ai(b, c);
        else if (c = hh(a, b, c, d), null !== c) {
          var e = R();
          gi(c, a, d, e);
          Bi(c, b, d);
        }
      }
      function ii(a, b, c) {
        var d = yi(a), e = { lane: d, action: c, hasEagerState: false, eagerState: null, next: null };
        if (zi(a)) Ai(b, e);
        else {
          var f = a.alternate;
          if (0 === a.lanes && (null === f || 0 === f.lanes) && (f = b.lastRenderedReducer, null !== f)) try {
            var g = b.lastRenderedState, h = f(g, c);
            e.hasEagerState = true;
            e.eagerState = h;
            if (He(h, g)) {
              var k = b.interleaved;
              null === k ? (e.next = e, gh(b)) : (e.next = k.next, k.next = e);
              b.interleaved = e;
              return;
            }
          } catch (l) {
          } finally {
          }
          c = hh(a, b, e, d);
          null !== c && (e = R(), gi(c, a, d, e), Bi(c, b, d));
        }
      }
      function zi(a) {
        var b = a.alternate;
        return a === M || null !== b && b === M;
      }
      function Ai(a, b) {
        Jh = Ih = true;
        var c = a.pending;
        null === c ? b.next = b : (b.next = c.next, c.next = b);
        a.pending = b;
      }
      function Bi(a, b, c) {
        if (0 !== (c & 4194240)) {
          var d = b.lanes;
          d &= a.pendingLanes;
          c |= d;
          b.lanes = c;
          Cc(a, c);
        }
      }
      var Rh = { readContext: eh, useCallback: P, useContext: P, useEffect: P, useImperativeHandle: P, useInsertionEffect: P, useLayoutEffect: P, useMemo: P, useReducer: P, useRef: P, useState: P, useDebugValue: P, useDeferredValue: P, useTransition: P, useMutableSource: P, useSyncExternalStore: P, useId: P, unstable_isNewReconciler: false };
      var Oh = { readContext: eh, useCallback: function(a, b) {
        Th().memoizedState = [a, void 0 === b ? null : b];
        return a;
      }, useContext: eh, useEffect: mi, useImperativeHandle: function(a, b, c) {
        c = null !== c && void 0 !== c ? c.concat([a]) : null;
        return ki(
          4194308,
          4,
          pi.bind(null, b, a),
          c
        );
      }, useLayoutEffect: function(a, b) {
        return ki(4194308, 4, a, b);
      }, useInsertionEffect: function(a, b) {
        return ki(4, 2, a, b);
      }, useMemo: function(a, b) {
        var c = Th();
        b = void 0 === b ? null : b;
        a = a();
        c.memoizedState = [a, b];
        return a;
      }, useReducer: function(a, b, c) {
        var d = Th();
        b = void 0 !== c ? c(b) : b;
        d.memoizedState = d.baseState = b;
        a = { pending: null, interleaved: null, lanes: 0, dispatch: null, lastRenderedReducer: a, lastRenderedState: b };
        d.queue = a;
        a = a.dispatch = xi.bind(null, M, a);
        return [d.memoizedState, a];
      }, useRef: function(a) {
        var b = Th();
        a = { current: a };
        return b.memoizedState = a;
      }, useState: hi, useDebugValue: ri, useDeferredValue: function(a) {
        return Th().memoizedState = a;
      }, useTransition: function() {
        var a = hi(false), b = a[0];
        a = vi.bind(null, a[1]);
        Th().memoizedState = a;
        return [b, a];
      }, useMutableSource: function() {
      }, useSyncExternalStore: function(a, b, c) {
        var d = M, e = Th();
        if (I) {
          if (void 0 === c) throw Error(p(407));
          c = c();
        } else {
          c = b();
          if (null === Q) throw Error(p(349));
          0 !== (Hh & 30) || di(d, b, c);
        }
        e.memoizedState = c;
        var f = { value: c, getSnapshot: b };
        e.queue = f;
        mi(ai.bind(
          null,
          d,
          f,
          a
        ), [a]);
        d.flags |= 2048;
        bi(9, ci.bind(null, d, f, c, b), void 0, null);
        return c;
      }, useId: function() {
        var a = Th(), b = Q.identifierPrefix;
        if (I) {
          var c = sg;
          var d = rg;
          c = (d & ~(1 << 32 - oc(d) - 1)).toString(32) + c;
          b = ":" + b + "R" + c;
          c = Kh++;
          0 < c && (b += "H" + c.toString(32));
          b += ":";
        } else c = Lh++, b = ":" + b + "r" + c.toString(32) + ":";
        return a.memoizedState = b;
      }, unstable_isNewReconciler: false };
      var Ph = {
        readContext: eh,
        useCallback: si,
        useContext: eh,
        useEffect: $h,
        useImperativeHandle: qi,
        useInsertionEffect: ni,
        useLayoutEffect: oi,
        useMemo: ti,
        useReducer: Wh,
        useRef: ji,
        useState: function() {
          return Wh(Vh);
        },
        useDebugValue: ri,
        useDeferredValue: function(a) {
          var b = Uh();
          return ui(b, N.memoizedState, a);
        },
        useTransition: function() {
          var a = Wh(Vh)[0], b = Uh().memoizedState;
          return [a, b];
        },
        useMutableSource: Yh,
        useSyncExternalStore: Zh,
        useId: wi,
        unstable_isNewReconciler: false
      };
      var Qh = { readContext: eh, useCallback: si, useContext: eh, useEffect: $h, useImperativeHandle: qi, useInsertionEffect: ni, useLayoutEffect: oi, useMemo: ti, useReducer: Xh, useRef: ji, useState: function() {
        return Xh(Vh);
      }, useDebugValue: ri, useDeferredValue: function(a) {
        var b = Uh();
        return null === N ? b.memoizedState = a : ui(b, N.memoizedState, a);
      }, useTransition: function() {
        var a = Xh(Vh)[0], b = Uh().memoizedState;
        return [a, b];
      }, useMutableSource: Yh, useSyncExternalStore: Zh, useId: wi, unstable_isNewReconciler: false };
      function Ci(a, b) {
        if (a && a.defaultProps) {
          b = A({}, b);
          a = a.defaultProps;
          for (var c in a) void 0 === b[c] && (b[c] = a[c]);
          return b;
        }
        return b;
      }
      function Di(a, b, c, d) {
        b = a.memoizedState;
        c = c(d, b);
        c = null === c || void 0 === c ? b : A({}, b, c);
        a.memoizedState = c;
        0 === a.lanes && (a.updateQueue.baseState = c);
      }
      var Ei = { isMounted: function(a) {
        return (a = a._reactInternals) ? Vb(a) === a : false;
      }, enqueueSetState: function(a, b, c) {
        a = a._reactInternals;
        var d = R(), e = yi(a), f = mh(d, e);
        f.payload = b;
        void 0 !== c && null !== c && (f.callback = c);
        b = nh(a, f, e);
        null !== b && (gi(b, a, e, d), oh(b, a, e));
      }, enqueueReplaceState: function(a, b, c) {
        a = a._reactInternals;
        var d = R(), e = yi(a), f = mh(d, e);
        f.tag = 1;
        f.payload = b;
        void 0 !== c && null !== c && (f.callback = c);
        b = nh(a, f, e);
        null !== b && (gi(b, a, e, d), oh(b, a, e));
      }, enqueueForceUpdate: function(a, b) {
        a = a._reactInternals;
        var c = R(), d = yi(a), e = mh(c, d);
        e.tag = 2;
        void 0 !== b && null !== b && (e.callback = b);
        b = nh(a, e, d);
        null !== b && (gi(b, a, d, c), oh(b, a, d));
      } };
      function Fi(a, b, c, d, e, f, g) {
        a = a.stateNode;
        return "function" === typeof a.shouldComponentUpdate ? a.shouldComponentUpdate(d, f, g) : b.prototype && b.prototype.isPureReactComponent ? !Ie(c, d) || !Ie(e, f) : true;
      }
      function Gi(a, b, c) {
        var d = false, e = Vf;
        var f = b.contextType;
        "object" === typeof f && null !== f ? f = eh(f) : (e = Zf(b) ? Xf : H.current, d = b.contextTypes, f = (d = null !== d && void 0 !== d) ? Yf(a, e) : Vf);
        b = new b(c, f);
        a.memoizedState = null !== b.state && void 0 !== b.state ? b.state : null;
        b.updater = Ei;
        a.stateNode = b;
        b._reactInternals = a;
        d && (a = a.stateNode, a.__reactInternalMemoizedUnmaskedChildContext = e, a.__reactInternalMemoizedMaskedChildContext = f);
        return b;
      }
      function Hi(a, b, c, d) {
        a = b.state;
        "function" === typeof b.componentWillReceiveProps && b.componentWillReceiveProps(c, d);
        "function" === typeof b.UNSAFE_componentWillReceiveProps && b.UNSAFE_componentWillReceiveProps(c, d);
        b.state !== a && Ei.enqueueReplaceState(b, b.state, null);
      }
      function Ii(a, b, c, d) {
        var e = a.stateNode;
        e.props = c;
        e.state = a.memoizedState;
        e.refs = {};
        kh(a);
        var f = b.contextType;
        "object" === typeof f && null !== f ? e.context = eh(f) : (f = Zf(b) ? Xf : H.current, e.context = Yf(a, f));
        e.state = a.memoizedState;
        f = b.getDerivedStateFromProps;
        "function" === typeof f && (Di(a, b, f, c), e.state = a.memoizedState);
        "function" === typeof b.getDerivedStateFromProps || "function" === typeof e.getSnapshotBeforeUpdate || "function" !== typeof e.UNSAFE_componentWillMount && "function" !== typeof e.componentWillMount || (b = e.state, "function" === typeof e.componentWillMount && e.componentWillMount(), "function" === typeof e.UNSAFE_componentWillMount && e.UNSAFE_componentWillMount(), b !== e.state && Ei.enqueueReplaceState(e, e.state, null), qh(a, c, e, d), e.state = a.memoizedState);
        "function" === typeof e.componentDidMount && (a.flags |= 4194308);
      }
      function Ji(a, b) {
        try {
          var c = "", d = b;
          do
            c += Pa(d), d = d.return;
          while (d);
          var e = c;
        } catch (f) {
          e = "\nError generating stack: " + f.message + "\n" + f.stack;
        }
        return { value: a, source: b, stack: e, digest: null };
      }
      function Ki(a, b, c) {
        return { value: a, source: null, stack: null != c ? c : null, digest: null != b ? b : null };
      }
      function Li(a, b) {
        try {
          console.error(b.value);
        } catch (c) {
          setTimeout(function() {
            throw c;
          });
        }
      }
      var Mi = "function" === typeof WeakMap ? WeakMap : Map;
      function Ni(a, b, c) {
        c = mh(-1, c);
        c.tag = 3;
        c.payload = { element: null };
        var d = b.value;
        c.callback = function() {
          Oi || (Oi = true, Pi = d);
          Li(a, b);
        };
        return c;
      }
      function Qi(a, b, c) {
        c = mh(-1, c);
        c.tag = 3;
        var d = a.type.getDerivedStateFromError;
        if ("function" === typeof d) {
          var e = b.value;
          c.payload = function() {
            return d(e);
          };
          c.callback = function() {
            Li(a, b);
          };
        }
        var f = a.stateNode;
        null !== f && "function" === typeof f.componentDidCatch && (c.callback = function() {
          Li(a, b);
          "function" !== typeof d && (null === Ri ? Ri = /* @__PURE__ */ new Set([this]) : Ri.add(this));
          var c2 = b.stack;
          this.componentDidCatch(b.value, { componentStack: null !== c2 ? c2 : "" });
        });
        return c;
      }
      function Si(a, b, c) {
        var d = a.pingCache;
        if (null === d) {
          d = a.pingCache = new Mi();
          var e = /* @__PURE__ */ new Set();
          d.set(b, e);
        } else e = d.get(b), void 0 === e && (e = /* @__PURE__ */ new Set(), d.set(b, e));
        e.has(c) || (e.add(c), a = Ti.bind(null, a, b, c), b.then(a, a));
      }
      function Ui(a) {
        do {
          var b;
          if (b = 13 === a.tag) b = a.memoizedState, b = null !== b ? null !== b.dehydrated ? true : false : true;
          if (b) return a;
          a = a.return;
        } while (null !== a);
        return null;
      }
      function Vi(a, b, c, d, e) {
        if (0 === (a.mode & 1)) return a === b ? a.flags |= 65536 : (a.flags |= 128, c.flags |= 131072, c.flags &= -52805, 1 === c.tag && (null === c.alternate ? c.tag = 17 : (b = mh(-1, 1), b.tag = 2, nh(c, b, 1))), c.lanes |= 1), a;
        a.flags |= 65536;
        a.lanes = e;
        return a;
      }
      var Wi = ua.ReactCurrentOwner;
      var dh = false;
      function Xi(a, b, c, d) {
        b.child = null === a ? Vg(b, null, c, d) : Ug(b, a.child, c, d);
      }
      function Yi(a, b, c, d, e) {
        c = c.render;
        var f = b.ref;
        ch(b, e);
        d = Nh(a, b, c, d, f, e);
        c = Sh();
        if (null !== a && !dh) return b.updateQueue = a.updateQueue, b.flags &= -2053, a.lanes &= ~e, Zi(a, b, e);
        I && c && vg(b);
        b.flags |= 1;
        Xi(a, b, d, e);
        return b.child;
      }
      function $i(a, b, c, d, e) {
        if (null === a) {
          var f = c.type;
          if ("function" === typeof f && !aj(f) && void 0 === f.defaultProps && null === c.compare && void 0 === c.defaultProps) return b.tag = 15, b.type = f, bj(a, b, f, d, e);
          a = Rg(c.type, null, d, b, b.mode, e);
          a.ref = b.ref;
          a.return = b;
          return b.child = a;
        }
        f = a.child;
        if (0 === (a.lanes & e)) {
          var g = f.memoizedProps;
          c = c.compare;
          c = null !== c ? c : Ie;
          if (c(g, d) && a.ref === b.ref) return Zi(a, b, e);
        }
        b.flags |= 1;
        a = Pg(f, d);
        a.ref = b.ref;
        a.return = b;
        return b.child = a;
      }
      function bj(a, b, c, d, e) {
        if (null !== a) {
          var f = a.memoizedProps;
          if (Ie(f, d) && a.ref === b.ref) if (dh = false, b.pendingProps = d = f, 0 !== (a.lanes & e)) 0 !== (a.flags & 131072) && (dh = true);
          else return b.lanes = a.lanes, Zi(a, b, e);
        }
        return cj(a, b, c, d, e);
      }
      function dj(a, b, c) {
        var d = b.pendingProps, e = d.children, f = null !== a ? a.memoizedState : null;
        if ("hidden" === d.mode) if (0 === (b.mode & 1)) b.memoizedState = { baseLanes: 0, cachePool: null, transitions: null }, G(ej, fj), fj |= c;
        else {
          if (0 === (c & 1073741824)) return a = null !== f ? f.baseLanes | c : c, b.lanes = b.childLanes = 1073741824, b.memoizedState = { baseLanes: a, cachePool: null, transitions: null }, b.updateQueue = null, G(ej, fj), fj |= a, null;
          b.memoizedState = { baseLanes: 0, cachePool: null, transitions: null };
          d = null !== f ? f.baseLanes : c;
          G(ej, fj);
          fj |= d;
        }
        else null !== f ? (d = f.baseLanes | c, b.memoizedState = null) : d = c, G(ej, fj), fj |= d;
        Xi(a, b, e, c);
        return b.child;
      }
      function gj(a, b) {
        var c = b.ref;
        if (null === a && null !== c || null !== a && a.ref !== c) b.flags |= 512, b.flags |= 2097152;
      }
      function cj(a, b, c, d, e) {
        var f = Zf(c) ? Xf : H.current;
        f = Yf(b, f);
        ch(b, e);
        c = Nh(a, b, c, d, f, e);
        d = Sh();
        if (null !== a && !dh) return b.updateQueue = a.updateQueue, b.flags &= -2053, a.lanes &= ~e, Zi(a, b, e);
        I && d && vg(b);
        b.flags |= 1;
        Xi(a, b, c, e);
        return b.child;
      }
      function hj(a, b, c, d, e) {
        if (Zf(c)) {
          var f = true;
          cg(b);
        } else f = false;
        ch(b, e);
        if (null === b.stateNode) ij(a, b), Gi(b, c, d), Ii(b, c, d, e), d = true;
        else if (null === a) {
          var g = b.stateNode, h = b.memoizedProps;
          g.props = h;
          var k = g.context, l = c.contextType;
          "object" === typeof l && null !== l ? l = eh(l) : (l = Zf(c) ? Xf : H.current, l = Yf(b, l));
          var m = c.getDerivedStateFromProps, q = "function" === typeof m || "function" === typeof g.getSnapshotBeforeUpdate;
          q || "function" !== typeof g.UNSAFE_componentWillReceiveProps && "function" !== typeof g.componentWillReceiveProps || (h !== d || k !== l) && Hi(b, g, d, l);
          jh = false;
          var r = b.memoizedState;
          g.state = r;
          qh(b, d, g, e);
          k = b.memoizedState;
          h !== d || r !== k || Wf.current || jh ? ("function" === typeof m && (Di(b, c, m, d), k = b.memoizedState), (h = jh || Fi(b, c, h, d, r, k, l)) ? (q || "function" !== typeof g.UNSAFE_componentWillMount && "function" !== typeof g.componentWillMount || ("function" === typeof g.componentWillMount && g.componentWillMount(), "function" === typeof g.UNSAFE_componentWillMount && g.UNSAFE_componentWillMount()), "function" === typeof g.componentDidMount && (b.flags |= 4194308)) : ("function" === typeof g.componentDidMount && (b.flags |= 4194308), b.memoizedProps = d, b.memoizedState = k), g.props = d, g.state = k, g.context = l, d = h) : ("function" === typeof g.componentDidMount && (b.flags |= 4194308), d = false);
        } else {
          g = b.stateNode;
          lh(a, b);
          h = b.memoizedProps;
          l = b.type === b.elementType ? h : Ci(b.type, h);
          g.props = l;
          q = b.pendingProps;
          r = g.context;
          k = c.contextType;
          "object" === typeof k && null !== k ? k = eh(k) : (k = Zf(c) ? Xf : H.current, k = Yf(b, k));
          var y = c.getDerivedStateFromProps;
          (m = "function" === typeof y || "function" === typeof g.getSnapshotBeforeUpdate) || "function" !== typeof g.UNSAFE_componentWillReceiveProps && "function" !== typeof g.componentWillReceiveProps || (h !== q || r !== k) && Hi(b, g, d, k);
          jh = false;
          r = b.memoizedState;
          g.state = r;
          qh(b, d, g, e);
          var n = b.memoizedState;
          h !== q || r !== n || Wf.current || jh ? ("function" === typeof y && (Di(b, c, y, d), n = b.memoizedState), (l = jh || Fi(b, c, l, d, r, n, k) || false) ? (m || "function" !== typeof g.UNSAFE_componentWillUpdate && "function" !== typeof g.componentWillUpdate || ("function" === typeof g.componentWillUpdate && g.componentWillUpdate(d, n, k), "function" === typeof g.UNSAFE_componentWillUpdate && g.UNSAFE_componentWillUpdate(d, n, k)), "function" === typeof g.componentDidUpdate && (b.flags |= 4), "function" === typeof g.getSnapshotBeforeUpdate && (b.flags |= 1024)) : ("function" !== typeof g.componentDidUpdate || h === a.memoizedProps && r === a.memoizedState || (b.flags |= 4), "function" !== typeof g.getSnapshotBeforeUpdate || h === a.memoizedProps && r === a.memoizedState || (b.flags |= 1024), b.memoizedProps = d, b.memoizedState = n), g.props = d, g.state = n, g.context = k, d = l) : ("function" !== typeof g.componentDidUpdate || h === a.memoizedProps && r === a.memoizedState || (b.flags |= 4), "function" !== typeof g.getSnapshotBeforeUpdate || h === a.memoizedProps && r === a.memoizedState || (b.flags |= 1024), d = false);
        }
        return jj(a, b, c, d, f, e);
      }
      function jj(a, b, c, d, e, f) {
        gj(a, b);
        var g = 0 !== (b.flags & 128);
        if (!d && !g) return e && dg(b, c, false), Zi(a, b, f);
        d = b.stateNode;
        Wi.current = b;
        var h = g && "function" !== typeof c.getDerivedStateFromError ? null : d.render();
        b.flags |= 1;
        null !== a && g ? (b.child = Ug(b, a.child, null, f), b.child = Ug(b, null, h, f)) : Xi(a, b, h, f);
        b.memoizedState = d.state;
        e && dg(b, c, true);
        return b.child;
      }
      function kj(a) {
        var b = a.stateNode;
        b.pendingContext ? ag(a, b.pendingContext, b.pendingContext !== b.context) : b.context && ag(a, b.context, false);
        yh(a, b.containerInfo);
      }
      function lj(a, b, c, d, e) {
        Ig();
        Jg(e);
        b.flags |= 256;
        Xi(a, b, c, d);
        return b.child;
      }
      var mj = { dehydrated: null, treeContext: null, retryLane: 0 };
      function nj(a) {
        return { baseLanes: a, cachePool: null, transitions: null };
      }
      function oj(a, b, c) {
        var d = b.pendingProps, e = L.current, f = false, g = 0 !== (b.flags & 128), h;
        (h = g) || (h = null !== a && null === a.memoizedState ? false : 0 !== (e & 2));
        if (h) f = true, b.flags &= -129;
        else if (null === a || null !== a.memoizedState) e |= 1;
        G(L, e & 1);
        if (null === a) {
          Eg(b);
          a = b.memoizedState;
          if (null !== a && (a = a.dehydrated, null !== a)) return 0 === (b.mode & 1) ? b.lanes = 1 : "$!" === a.data ? b.lanes = 8 : b.lanes = 1073741824, null;
          g = d.children;
          a = d.fallback;
          return f ? (d = b.mode, f = b.child, g = { mode: "hidden", children: g }, 0 === (d & 1) && null !== f ? (f.childLanes = 0, f.pendingProps = g) : f = pj(g, d, 0, null), a = Tg(a, d, c, null), f.return = b, a.return = b, f.sibling = a, b.child = f, b.child.memoizedState = nj(c), b.memoizedState = mj, a) : qj(b, g);
        }
        e = a.memoizedState;
        if (null !== e && (h = e.dehydrated, null !== h)) return rj(a, b, g, d, h, e, c);
        if (f) {
          f = d.fallback;
          g = b.mode;
          e = a.child;
          h = e.sibling;
          var k = { mode: "hidden", children: d.children };
          0 === (g & 1) && b.child !== e ? (d = b.child, d.childLanes = 0, d.pendingProps = k, b.deletions = null) : (d = Pg(e, k), d.subtreeFlags = e.subtreeFlags & 14680064);
          null !== h ? f = Pg(h, f) : (f = Tg(f, g, c, null), f.flags |= 2);
          f.return = b;
          d.return = b;
          d.sibling = f;
          b.child = d;
          d = f;
          f = b.child;
          g = a.child.memoizedState;
          g = null === g ? nj(c) : { baseLanes: g.baseLanes | c, cachePool: null, transitions: g.transitions };
          f.memoizedState = g;
          f.childLanes = a.childLanes & ~c;
          b.memoizedState = mj;
          return d;
        }
        f = a.child;
        a = f.sibling;
        d = Pg(f, { mode: "visible", children: d.children });
        0 === (b.mode & 1) && (d.lanes = c);
        d.return = b;
        d.sibling = null;
        null !== a && (c = b.deletions, null === c ? (b.deletions = [a], b.flags |= 16) : c.push(a));
        b.child = d;
        b.memoizedState = null;
        return d;
      }
      function qj(a, b) {
        b = pj({ mode: "visible", children: b }, a.mode, 0, null);
        b.return = a;
        return a.child = b;
      }
      function sj(a, b, c, d) {
        null !== d && Jg(d);
        Ug(b, a.child, null, c);
        a = qj(b, b.pendingProps.children);
        a.flags |= 2;
        b.memoizedState = null;
        return a;
      }
      function rj(a, b, c, d, e, f, g) {
        if (c) {
          if (b.flags & 256) return b.flags &= -257, d = Ki(Error(p(422))), sj(a, b, g, d);
          if (null !== b.memoizedState) return b.child = a.child, b.flags |= 128, null;
          f = d.fallback;
          e = b.mode;
          d = pj({ mode: "visible", children: d.children }, e, 0, null);
          f = Tg(f, e, g, null);
          f.flags |= 2;
          d.return = b;
          f.return = b;
          d.sibling = f;
          b.child = d;
          0 !== (b.mode & 1) && Ug(b, a.child, null, g);
          b.child.memoizedState = nj(g);
          b.memoizedState = mj;
          return f;
        }
        if (0 === (b.mode & 1)) return sj(a, b, g, null);
        if ("$!" === e.data) {
          d = e.nextSibling && e.nextSibling.dataset;
          if (d) var h = d.dgst;
          d = h;
          f = Error(p(419));
          d = Ki(f, d, void 0);
          return sj(a, b, g, d);
        }
        h = 0 !== (g & a.childLanes);
        if (dh || h) {
          d = Q;
          if (null !== d) {
            switch (g & -g) {
              case 4:
                e = 2;
                break;
              case 16:
                e = 8;
                break;
              case 64:
              case 128:
              case 256:
              case 512:
              case 1024:
              case 2048:
              case 4096:
              case 8192:
              case 16384:
              case 32768:
              case 65536:
              case 131072:
              case 262144:
              case 524288:
              case 1048576:
              case 2097152:
              case 4194304:
              case 8388608:
              case 16777216:
              case 33554432:
              case 67108864:
                e = 32;
                break;
              case 536870912:
                e = 268435456;
                break;
              default:
                e = 0;
            }
            e = 0 !== (e & (d.suspendedLanes | g)) ? 0 : e;
            0 !== e && e !== f.retryLane && (f.retryLane = e, ih(a, e), gi(d, a, e, -1));
          }
          tj();
          d = Ki(Error(p(421)));
          return sj(a, b, g, d);
        }
        if ("$?" === e.data) return b.flags |= 128, b.child = a.child, b = uj.bind(null, a), e._reactRetry = b, null;
        a = f.treeContext;
        yg = Lf(e.nextSibling);
        xg = b;
        I = true;
        zg = null;
        null !== a && (og[pg++] = rg, og[pg++] = sg, og[pg++] = qg, rg = a.id, sg = a.overflow, qg = b);
        b = qj(b, d.children);
        b.flags |= 4096;
        return b;
      }
      function vj(a, b, c) {
        a.lanes |= b;
        var d = a.alternate;
        null !== d && (d.lanes |= b);
        bh(a.return, b, c);
      }
      function wj(a, b, c, d, e) {
        var f = a.memoizedState;
        null === f ? a.memoizedState = { isBackwards: b, rendering: null, renderingStartTime: 0, last: d, tail: c, tailMode: e } : (f.isBackwards = b, f.rendering = null, f.renderingStartTime = 0, f.last = d, f.tail = c, f.tailMode = e);
      }
      function xj(a, b, c) {
        var d = b.pendingProps, e = d.revealOrder, f = d.tail;
        Xi(a, b, d.children, c);
        d = L.current;
        if (0 !== (d & 2)) d = d & 1 | 2, b.flags |= 128;
        else {
          if (null !== a && 0 !== (a.flags & 128)) a: for (a = b.child; null !== a; ) {
            if (13 === a.tag) null !== a.memoizedState && vj(a, c, b);
            else if (19 === a.tag) vj(a, c, b);
            else if (null !== a.child) {
              a.child.return = a;
              a = a.child;
              continue;
            }
            if (a === b) break a;
            for (; null === a.sibling; ) {
              if (null === a.return || a.return === b) break a;
              a = a.return;
            }
            a.sibling.return = a.return;
            a = a.sibling;
          }
          d &= 1;
        }
        G(L, d);
        if (0 === (b.mode & 1)) b.memoizedState = null;
        else switch (e) {
          case "forwards":
            c = b.child;
            for (e = null; null !== c; ) a = c.alternate, null !== a && null === Ch(a) && (e = c), c = c.sibling;
            c = e;
            null === c ? (e = b.child, b.child = null) : (e = c.sibling, c.sibling = null);
            wj(b, false, e, c, f);
            break;
          case "backwards":
            c = null;
            e = b.child;
            for (b.child = null; null !== e; ) {
              a = e.alternate;
              if (null !== a && null === Ch(a)) {
                b.child = e;
                break;
              }
              a = e.sibling;
              e.sibling = c;
              c = e;
              e = a;
            }
            wj(b, true, c, null, f);
            break;
          case "together":
            wj(b, false, null, null, void 0);
            break;
          default:
            b.memoizedState = null;
        }
        return b.child;
      }
      function ij(a, b) {
        0 === (b.mode & 1) && null !== a && (a.alternate = null, b.alternate = null, b.flags |= 2);
      }
      function Zi(a, b, c) {
        null !== a && (b.dependencies = a.dependencies);
        rh |= b.lanes;
        if (0 === (c & b.childLanes)) return null;
        if (null !== a && b.child !== a.child) throw Error(p(153));
        if (null !== b.child) {
          a = b.child;
          c = Pg(a, a.pendingProps);
          b.child = c;
          for (c.return = b; null !== a.sibling; ) a = a.sibling, c = c.sibling = Pg(a, a.pendingProps), c.return = b;
          c.sibling = null;
        }
        return b.child;
      }
      function yj(a, b, c) {
        switch (b.tag) {
          case 3:
            kj(b);
            Ig();
            break;
          case 5:
            Ah(b);
            break;
          case 1:
            Zf(b.type) && cg(b);
            break;
          case 4:
            yh(b, b.stateNode.containerInfo);
            break;
          case 10:
            var d = b.type._context, e = b.memoizedProps.value;
            G(Wg, d._currentValue);
            d._currentValue = e;
            break;
          case 13:
            d = b.memoizedState;
            if (null !== d) {
              if (null !== d.dehydrated) return G(L, L.current & 1), b.flags |= 128, null;
              if (0 !== (c & b.child.childLanes)) return oj(a, b, c);
              G(L, L.current & 1);
              a = Zi(a, b, c);
              return null !== a ? a.sibling : null;
            }
            G(L, L.current & 1);
            break;
          case 19:
            d = 0 !== (c & b.childLanes);
            if (0 !== (a.flags & 128)) {
              if (d) return xj(a, b, c);
              b.flags |= 128;
            }
            e = b.memoizedState;
            null !== e && (e.rendering = null, e.tail = null, e.lastEffect = null);
            G(L, L.current);
            if (d) break;
            else return null;
          case 22:
          case 23:
            return b.lanes = 0, dj(a, b, c);
        }
        return Zi(a, b, c);
      }
      var zj;
      var Aj;
      var Bj;
      var Cj;
      zj = function(a, b) {
        for (var c = b.child; null !== c; ) {
          if (5 === c.tag || 6 === c.tag) a.appendChild(c.stateNode);
          else if (4 !== c.tag && null !== c.child) {
            c.child.return = c;
            c = c.child;
            continue;
          }
          if (c === b) break;
          for (; null === c.sibling; ) {
            if (null === c.return || c.return === b) return;
            c = c.return;
          }
          c.sibling.return = c.return;
          c = c.sibling;
        }
      };
      Aj = function() {
      };
      Bj = function(a, b, c, d) {
        var e = a.memoizedProps;
        if (e !== d) {
          a = b.stateNode;
          xh(uh.current);
          var f = null;
          switch (c) {
            case "input":
              e = Ya(a, e);
              d = Ya(a, d);
              f = [];
              break;
            case "select":
              e = A({}, e, { value: void 0 });
              d = A({}, d, { value: void 0 });
              f = [];
              break;
            case "textarea":
              e = gb(a, e);
              d = gb(a, d);
              f = [];
              break;
            default:
              "function" !== typeof e.onClick && "function" === typeof d.onClick && (a.onclick = Bf);
          }
          ub(c, d);
          var g;
          c = null;
          for (l in e) if (!d.hasOwnProperty(l) && e.hasOwnProperty(l) && null != e[l]) if ("style" === l) {
            var h = e[l];
            for (g in h) h.hasOwnProperty(g) && (c || (c = {}), c[g] = "");
          } else "dangerouslySetInnerHTML" !== l && "children" !== l && "suppressContentEditableWarning" !== l && "suppressHydrationWarning" !== l && "autoFocus" !== l && (ea.hasOwnProperty(l) ? f || (f = []) : (f = f || []).push(l, null));
          for (l in d) {
            var k = d[l];
            h = null != e ? e[l] : void 0;
            if (d.hasOwnProperty(l) && k !== h && (null != k || null != h)) if ("style" === l) if (h) {
              for (g in h) !h.hasOwnProperty(g) || k && k.hasOwnProperty(g) || (c || (c = {}), c[g] = "");
              for (g in k) k.hasOwnProperty(g) && h[g] !== k[g] && (c || (c = {}), c[g] = k[g]);
            } else c || (f || (f = []), f.push(
              l,
              c
            )), c = k;
            else "dangerouslySetInnerHTML" === l ? (k = k ? k.__html : void 0, h = h ? h.__html : void 0, null != k && h !== k && (f = f || []).push(l, k)) : "children" === l ? "string" !== typeof k && "number" !== typeof k || (f = f || []).push(l, "" + k) : "suppressContentEditableWarning" !== l && "suppressHydrationWarning" !== l && (ea.hasOwnProperty(l) ? (null != k && "onScroll" === l && D("scroll", a), f || h === k || (f = [])) : (f = f || []).push(l, k));
          }
          c && (f = f || []).push("style", c);
          var l = f;
          if (b.updateQueue = l) b.flags |= 4;
        }
      };
      Cj = function(a, b, c, d) {
        c !== d && (b.flags |= 4);
      };
      function Dj(a, b) {
        if (!I) switch (a.tailMode) {
          case "hidden":
            b = a.tail;
            for (var c = null; null !== b; ) null !== b.alternate && (c = b), b = b.sibling;
            null === c ? a.tail = null : c.sibling = null;
            break;
          case "collapsed":
            c = a.tail;
            for (var d = null; null !== c; ) null !== c.alternate && (d = c), c = c.sibling;
            null === d ? b || null === a.tail ? a.tail = null : a.tail.sibling = null : d.sibling = null;
        }
      }
      function S(a) {
        var b = null !== a.alternate && a.alternate.child === a.child, c = 0, d = 0;
        if (b) for (var e = a.child; null !== e; ) c |= e.lanes | e.childLanes, d |= e.subtreeFlags & 14680064, d |= e.flags & 14680064, e.return = a, e = e.sibling;
        else for (e = a.child; null !== e; ) c |= e.lanes | e.childLanes, d |= e.subtreeFlags, d |= e.flags, e.return = a, e = e.sibling;
        a.subtreeFlags |= d;
        a.childLanes = c;
        return b;
      }
      function Ej(a, b, c) {
        var d = b.pendingProps;
        wg(b);
        switch (b.tag) {
          case 2:
          case 16:
          case 15:
          case 0:
          case 11:
          case 7:
          case 8:
          case 12:
          case 9:
          case 14:
            return S(b), null;
          case 1:
            return Zf(b.type) && $f(), S(b), null;
          case 3:
            d = b.stateNode;
            zh();
            E(Wf);
            E(H);
            Eh();
            d.pendingContext && (d.context = d.pendingContext, d.pendingContext = null);
            if (null === a || null === a.child) Gg(b) ? b.flags |= 4 : null === a || a.memoizedState.isDehydrated && 0 === (b.flags & 256) || (b.flags |= 1024, null !== zg && (Fj(zg), zg = null));
            Aj(a, b);
            S(b);
            return null;
          case 5:
            Bh(b);
            var e = xh(wh.current);
            c = b.type;
            if (null !== a && null != b.stateNode) Bj(a, b, c, d, e), a.ref !== b.ref && (b.flags |= 512, b.flags |= 2097152);
            else {
              if (!d) {
                if (null === b.stateNode) throw Error(p(166));
                S(b);
                return null;
              }
              a = xh(uh.current);
              if (Gg(b)) {
                d = b.stateNode;
                c = b.type;
                var f = b.memoizedProps;
                d[Of] = b;
                d[Pf] = f;
                a = 0 !== (b.mode & 1);
                switch (c) {
                  case "dialog":
                    D("cancel", d);
                    D("close", d);
                    break;
                  case "iframe":
                  case "object":
                  case "embed":
                    D("load", d);
                    break;
                  case "video":
                  case "audio":
                    for (e = 0; e < lf.length; e++) D(lf[e], d);
                    break;
                  case "source":
                    D("error", d);
                    break;
                  case "img":
                  case "image":
                  case "link":
                    D(
                      "error",
                      d
                    );
                    D("load", d);
                    break;
                  case "details":
                    D("toggle", d);
                    break;
                  case "input":
                    Za(d, f);
                    D("invalid", d);
                    break;
                  case "select":
                    d._wrapperState = { wasMultiple: !!f.multiple };
                    D("invalid", d);
                    break;
                  case "textarea":
                    hb(d, f), D("invalid", d);
                }
                ub(c, f);
                e = null;
                for (var g in f) if (f.hasOwnProperty(g)) {
                  var h = f[g];
                  "children" === g ? "string" === typeof h ? d.textContent !== h && (true !== f.suppressHydrationWarning && Af(d.textContent, h, a), e = ["children", h]) : "number" === typeof h && d.textContent !== "" + h && (true !== f.suppressHydrationWarning && Af(
                    d.textContent,
                    h,
                    a
                  ), e = ["children", "" + h]) : ea.hasOwnProperty(g) && null != h && "onScroll" === g && D("scroll", d);
                }
                switch (c) {
                  case "input":
                    Va(d);
                    db(d, f, true);
                    break;
                  case "textarea":
                    Va(d);
                    jb(d);
                    break;
                  case "select":
                  case "option":
                    break;
                  default:
                    "function" === typeof f.onClick && (d.onclick = Bf);
                }
                d = e;
                b.updateQueue = d;
                null !== d && (b.flags |= 4);
              } else {
                g = 9 === e.nodeType ? e : e.ownerDocument;
                "http://www.w3.org/1999/xhtml" === a && (a = kb(c));
                "http://www.w3.org/1999/xhtml" === a ? "script" === c ? (a = g.createElement("div"), a.innerHTML = "<script><\/script>", a = a.removeChild(a.firstChild)) : "string" === typeof d.is ? a = g.createElement(c, { is: d.is }) : (a = g.createElement(c), "select" === c && (g = a, d.multiple ? g.multiple = true : d.size && (g.size = d.size))) : a = g.createElementNS(a, c);
                a[Of] = b;
                a[Pf] = d;
                zj(a, b, false, false);
                b.stateNode = a;
                a: {
                  g = vb(c, d);
                  switch (c) {
                    case "dialog":
                      D("cancel", a);
                      D("close", a);
                      e = d;
                      break;
                    case "iframe":
                    case "object":
                    case "embed":
                      D("load", a);
                      e = d;
                      break;
                    case "video":
                    case "audio":
                      for (e = 0; e < lf.length; e++) D(lf[e], a);
                      e = d;
                      break;
                    case "source":
                      D("error", a);
                      e = d;
                      break;
                    case "img":
                    case "image":
                    case "link":
                      D(
                        "error",
                        a
                      );
                      D("load", a);
                      e = d;
                      break;
                    case "details":
                      D("toggle", a);
                      e = d;
                      break;
                    case "input":
                      Za(a, d);
                      e = Ya(a, d);
                      D("invalid", a);
                      break;
                    case "option":
                      e = d;
                      break;
                    case "select":
                      a._wrapperState = { wasMultiple: !!d.multiple };
                      e = A({}, d, { value: void 0 });
                      D("invalid", a);
                      break;
                    case "textarea":
                      hb(a, d);
                      e = gb(a, d);
                      D("invalid", a);
                      break;
                    default:
                      e = d;
                  }
                  ub(c, e);
                  h = e;
                  for (f in h) if (h.hasOwnProperty(f)) {
                    var k = h[f];
                    "style" === f ? sb(a, k) : "dangerouslySetInnerHTML" === f ? (k = k ? k.__html : void 0, null != k && nb(a, k)) : "children" === f ? "string" === typeof k ? ("textarea" !== c || "" !== k) && ob(a, k) : "number" === typeof k && ob(a, "" + k) : "suppressContentEditableWarning" !== f && "suppressHydrationWarning" !== f && "autoFocus" !== f && (ea.hasOwnProperty(f) ? null != k && "onScroll" === f && D("scroll", a) : null != k && ta(a, f, k, g));
                  }
                  switch (c) {
                    case "input":
                      Va(a);
                      db(a, d, false);
                      break;
                    case "textarea":
                      Va(a);
                      jb(a);
                      break;
                    case "option":
                      null != d.value && a.setAttribute("value", "" + Sa(d.value));
                      break;
                    case "select":
                      a.multiple = !!d.multiple;
                      f = d.value;
                      null != f ? fb(a, !!d.multiple, f, false) : null != d.defaultValue && fb(
                        a,
                        !!d.multiple,
                        d.defaultValue,
                        true
                      );
                      break;
                    default:
                      "function" === typeof e.onClick && (a.onclick = Bf);
                  }
                  switch (c) {
                    case "button":
                    case "input":
                    case "select":
                    case "textarea":
                      d = !!d.autoFocus;
                      break a;
                    case "img":
                      d = true;
                      break a;
                    default:
                      d = false;
                  }
                }
                d && (b.flags |= 4);
              }
              null !== b.ref && (b.flags |= 512, b.flags |= 2097152);
            }
            S(b);
            return null;
          case 6:
            if (a && null != b.stateNode) Cj(a, b, a.memoizedProps, d);
            else {
              if ("string" !== typeof d && null === b.stateNode) throw Error(p(166));
              c = xh(wh.current);
              xh(uh.current);
              if (Gg(b)) {
                d = b.stateNode;
                c = b.memoizedProps;
                d[Of] = b;
                if (f = d.nodeValue !== c) {
                  if (a = xg, null !== a) switch (a.tag) {
                    case 3:
                      Af(d.nodeValue, c, 0 !== (a.mode & 1));
                      break;
                    case 5:
                      true !== a.memoizedProps.suppressHydrationWarning && Af(d.nodeValue, c, 0 !== (a.mode & 1));
                  }
                }
                f && (b.flags |= 4);
              } else d = (9 === c.nodeType ? c : c.ownerDocument).createTextNode(d), d[Of] = b, b.stateNode = d;
            }
            S(b);
            return null;
          case 13:
            E(L);
            d = b.memoizedState;
            if (null === a || null !== a.memoizedState && null !== a.memoizedState.dehydrated) {
              if (I && null !== yg && 0 !== (b.mode & 1) && 0 === (b.flags & 128)) Hg(), Ig(), b.flags |= 98560, f = false;
              else if (f = Gg(b), null !== d && null !== d.dehydrated) {
                if (null === a) {
                  if (!f) throw Error(p(318));
                  f = b.memoizedState;
                  f = null !== f ? f.dehydrated : null;
                  if (!f) throw Error(p(317));
                  f[Of] = b;
                } else Ig(), 0 === (b.flags & 128) && (b.memoizedState = null), b.flags |= 4;
                S(b);
                f = false;
              } else null !== zg && (Fj(zg), zg = null), f = true;
              if (!f) return b.flags & 65536 ? b : null;
            }
            if (0 !== (b.flags & 128)) return b.lanes = c, b;
            d = null !== d;
            d !== (null !== a && null !== a.memoizedState) && d && (b.child.flags |= 8192, 0 !== (b.mode & 1) && (null === a || 0 !== (L.current & 1) ? 0 === T && (T = 3) : tj()));
            null !== b.updateQueue && (b.flags |= 4);
            S(b);
            return null;
          case 4:
            return zh(), Aj(a, b), null === a && sf(b.stateNode.containerInfo), S(b), null;
          case 10:
            return ah(b.type._context), S(b), null;
          case 17:
            return Zf(b.type) && $f(), S(b), null;
          case 19:
            E(L);
            f = b.memoizedState;
            if (null === f) return S(b), null;
            d = 0 !== (b.flags & 128);
            g = f.rendering;
            if (null === g) if (d) Dj(f, false);
            else {
              if (0 !== T || null !== a && 0 !== (a.flags & 128)) for (a = b.child; null !== a; ) {
                g = Ch(a);
                if (null !== g) {
                  b.flags |= 128;
                  Dj(f, false);
                  d = g.updateQueue;
                  null !== d && (b.updateQueue = d, b.flags |= 4);
                  b.subtreeFlags = 0;
                  d = c;
                  for (c = b.child; null !== c; ) f = c, a = d, f.flags &= 14680066, g = f.alternate, null === g ? (f.childLanes = 0, f.lanes = a, f.child = null, f.subtreeFlags = 0, f.memoizedProps = null, f.memoizedState = null, f.updateQueue = null, f.dependencies = null, f.stateNode = null) : (f.childLanes = g.childLanes, f.lanes = g.lanes, f.child = g.child, f.subtreeFlags = 0, f.deletions = null, f.memoizedProps = g.memoizedProps, f.memoizedState = g.memoizedState, f.updateQueue = g.updateQueue, f.type = g.type, a = g.dependencies, f.dependencies = null === a ? null : { lanes: a.lanes, firstContext: a.firstContext }), c = c.sibling;
                  G(L, L.current & 1 | 2);
                  return b.child;
                }
                a = a.sibling;
              }
              null !== f.tail && B() > Gj && (b.flags |= 128, d = true, Dj(f, false), b.lanes = 4194304);
            }
            else {
              if (!d) if (a = Ch(g), null !== a) {
                if (b.flags |= 128, d = true, c = a.updateQueue, null !== c && (b.updateQueue = c, b.flags |= 4), Dj(f, true), null === f.tail && "hidden" === f.tailMode && !g.alternate && !I) return S(b), null;
              } else 2 * B() - f.renderingStartTime > Gj && 1073741824 !== c && (b.flags |= 128, d = true, Dj(f, false), b.lanes = 4194304);
              f.isBackwards ? (g.sibling = b.child, b.child = g) : (c = f.last, null !== c ? c.sibling = g : b.child = g, f.last = g);
            }
            if (null !== f.tail) return b = f.tail, f.rendering = b, f.tail = b.sibling, f.renderingStartTime = B(), b.sibling = null, c = L.current, G(L, d ? c & 1 | 2 : c & 1), b;
            S(b);
            return null;
          case 22:
          case 23:
            return Hj(), d = null !== b.memoizedState, null !== a && null !== a.memoizedState !== d && (b.flags |= 8192), d && 0 !== (b.mode & 1) ? 0 !== (fj & 1073741824) && (S(b), b.subtreeFlags & 6 && (b.flags |= 8192)) : S(b), null;
          case 24:
            return null;
          case 25:
            return null;
        }
        throw Error(p(156, b.tag));
      }
      function Ij(a, b) {
        wg(b);
        switch (b.tag) {
          case 1:
            return Zf(b.type) && $f(), a = b.flags, a & 65536 ? (b.flags = a & -65537 | 128, b) : null;
          case 3:
            return zh(), E(Wf), E(H), Eh(), a = b.flags, 0 !== (a & 65536) && 0 === (a & 128) ? (b.flags = a & -65537 | 128, b) : null;
          case 5:
            return Bh(b), null;
          case 13:
            E(L);
            a = b.memoizedState;
            if (null !== a && null !== a.dehydrated) {
              if (null === b.alternate) throw Error(p(340));
              Ig();
            }
            a = b.flags;
            return a & 65536 ? (b.flags = a & -65537 | 128, b) : null;
          case 19:
            return E(L), null;
          case 4:
            return zh(), null;
          case 10:
            return ah(b.type._context), null;
          case 22:
          case 23:
            return Hj(), null;
          case 24:
            return null;
          default:
            return null;
        }
      }
      var Jj = false;
      var U = false;
      var Kj = "function" === typeof WeakSet ? WeakSet : Set;
      var V = null;
      function Lj(a, b) {
        var c = a.ref;
        if (null !== c) if ("function" === typeof c) try {
          c(null);
        } catch (d) {
          W(a, b, d);
        }
        else c.current = null;
      }
      function Mj(a, b, c) {
        try {
          c();
        } catch (d) {
          W(a, b, d);
        }
      }
      var Nj = false;
      function Oj(a, b) {
        Cf = dd;
        a = Me();
        if (Ne(a)) {
          if ("selectionStart" in a) var c = { start: a.selectionStart, end: a.selectionEnd };
          else a: {
            c = (c = a.ownerDocument) && c.defaultView || window;
            var d = c.getSelection && c.getSelection();
            if (d && 0 !== d.rangeCount) {
              c = d.anchorNode;
              var e = d.anchorOffset, f = d.focusNode;
              d = d.focusOffset;
              try {
                c.nodeType, f.nodeType;
              } catch (F) {
                c = null;
                break a;
              }
              var g = 0, h = -1, k = -1, l = 0, m = 0, q = a, r = null;
              b: for (; ; ) {
                for (var y; ; ) {
                  q !== c || 0 !== e && 3 !== q.nodeType || (h = g + e);
                  q !== f || 0 !== d && 3 !== q.nodeType || (k = g + d);
                  3 === q.nodeType && (g += q.nodeValue.length);
                  if (null === (y = q.firstChild)) break;
                  r = q;
                  q = y;
                }
                for (; ; ) {
                  if (q === a) break b;
                  r === c && ++l === e && (h = g);
                  r === f && ++m === d && (k = g);
                  if (null !== (y = q.nextSibling)) break;
                  q = r;
                  r = q.parentNode;
                }
                q = y;
              }
              c = -1 === h || -1 === k ? null : { start: h, end: k };
            } else c = null;
          }
          c = c || { start: 0, end: 0 };
        } else c = null;
        Df = { focusedElem: a, selectionRange: c };
        dd = false;
        for (V = b; null !== V; ) if (b = V, a = b.child, 0 !== (b.subtreeFlags & 1028) && null !== a) a.return = b, V = a;
        else for (; null !== V; ) {
          b = V;
          try {
            var n = b.alternate;
            if (0 !== (b.flags & 1024)) switch (b.tag) {
              case 0:
              case 11:
              case 15:
                break;
              case 1:
                if (null !== n) {
                  var t = n.memoizedProps, J = n.memoizedState, x = b.stateNode, w = x.getSnapshotBeforeUpdate(b.elementType === b.type ? t : Ci(b.type, t), J);
                  x.__reactInternalSnapshotBeforeUpdate = w;
                }
                break;
              case 3:
                var u = b.stateNode.containerInfo;
                1 === u.nodeType ? u.textContent = "" : 9 === u.nodeType && u.documentElement && u.removeChild(u.documentElement);
                break;
              case 5:
              case 6:
              case 4:
              case 17:
                break;
              default:
                throw Error(p(163));
            }
          } catch (F) {
            W(b, b.return, F);
          }
          a = b.sibling;
          if (null !== a) {
            a.return = b.return;
            V = a;
            break;
          }
          V = b.return;
        }
        n = Nj;
        Nj = false;
        return n;
      }
      function Pj(a, b, c) {
        var d = b.updateQueue;
        d = null !== d ? d.lastEffect : null;
        if (null !== d) {
          var e = d = d.next;
          do {
            if ((e.tag & a) === a) {
              var f = e.destroy;
              e.destroy = void 0;
              void 0 !== f && Mj(b, c, f);
            }
            e = e.next;
          } while (e !== d);
        }
      }
      function Qj(a, b) {
        b = b.updateQueue;
        b = null !== b ? b.lastEffect : null;
        if (null !== b) {
          var c = b = b.next;
          do {
            if ((c.tag & a) === a) {
              var d = c.create;
              c.destroy = d();
            }
            c = c.next;
          } while (c !== b);
        }
      }
      function Rj(a) {
        var b = a.ref;
        if (null !== b) {
          var c = a.stateNode;
          switch (a.tag) {
            case 5:
              a = c;
              break;
            default:
              a = c;
          }
          "function" === typeof b ? b(a) : b.current = a;
        }
      }
      function Sj(a) {
        var b = a.alternate;
        null !== b && (a.alternate = null, Sj(b));
        a.child = null;
        a.deletions = null;
        a.sibling = null;
        5 === a.tag && (b = a.stateNode, null !== b && (delete b[Of], delete b[Pf], delete b[of], delete b[Qf], delete b[Rf]));
        a.stateNode = null;
        a.return = null;
        a.dependencies = null;
        a.memoizedProps = null;
        a.memoizedState = null;
        a.pendingProps = null;
        a.stateNode = null;
        a.updateQueue = null;
      }
      function Tj(a) {
        return 5 === a.tag || 3 === a.tag || 4 === a.tag;
      }
      function Uj(a) {
        a: for (; ; ) {
          for (; null === a.sibling; ) {
            if (null === a.return || Tj(a.return)) return null;
            a = a.return;
          }
          a.sibling.return = a.return;
          for (a = a.sibling; 5 !== a.tag && 6 !== a.tag && 18 !== a.tag; ) {
            if (a.flags & 2) continue a;
            if (null === a.child || 4 === a.tag) continue a;
            else a.child.return = a, a = a.child;
          }
          if (!(a.flags & 2)) return a.stateNode;
        }
      }
      function Vj(a, b, c) {
        var d = a.tag;
        if (5 === d || 6 === d) a = a.stateNode, b ? 8 === c.nodeType ? c.parentNode.insertBefore(a, b) : c.insertBefore(a, b) : (8 === c.nodeType ? (b = c.parentNode, b.insertBefore(a, c)) : (b = c, b.appendChild(a)), c = c._reactRootContainer, null !== c && void 0 !== c || null !== b.onclick || (b.onclick = Bf));
        else if (4 !== d && (a = a.child, null !== a)) for (Vj(a, b, c), a = a.sibling; null !== a; ) Vj(a, b, c), a = a.sibling;
      }
      function Wj(a, b, c) {
        var d = a.tag;
        if (5 === d || 6 === d) a = a.stateNode, b ? c.insertBefore(a, b) : c.appendChild(a);
        else if (4 !== d && (a = a.child, null !== a)) for (Wj(a, b, c), a = a.sibling; null !== a; ) Wj(a, b, c), a = a.sibling;
      }
      var X2 = null;
      var Xj = false;
      function Yj(a, b, c) {
        for (c = c.child; null !== c; ) Zj(a, b, c), c = c.sibling;
      }
      function Zj(a, b, c) {
        if (lc && "function" === typeof lc.onCommitFiberUnmount) try {
          lc.onCommitFiberUnmount(kc, c);
        } catch (h) {
        }
        switch (c.tag) {
          case 5:
            U || Lj(c, b);
          case 6:
            var d = X2, e = Xj;
            X2 = null;
            Yj(a, b, c);
            X2 = d;
            Xj = e;
            null !== X2 && (Xj ? (a = X2, c = c.stateNode, 8 === a.nodeType ? a.parentNode.removeChild(c) : a.removeChild(c)) : X2.removeChild(c.stateNode));
            break;
          case 18:
            null !== X2 && (Xj ? (a = X2, c = c.stateNode, 8 === a.nodeType ? Kf(a.parentNode, c) : 1 === a.nodeType && Kf(a, c), bd(a)) : Kf(X2, c.stateNode));
            break;
          case 4:
            d = X2;
            e = Xj;
            X2 = c.stateNode.containerInfo;
            Xj = true;
            Yj(a, b, c);
            X2 = d;
            Xj = e;
            break;
          case 0:
          case 11:
          case 14:
          case 15:
            if (!U && (d = c.updateQueue, null !== d && (d = d.lastEffect, null !== d))) {
              e = d = d.next;
              do {
                var f = e, g = f.destroy;
                f = f.tag;
                void 0 !== g && (0 !== (f & 2) ? Mj(c, b, g) : 0 !== (f & 4) && Mj(c, b, g));
                e = e.next;
              } while (e !== d);
            }
            Yj(a, b, c);
            break;
          case 1:
            if (!U && (Lj(c, b), d = c.stateNode, "function" === typeof d.componentWillUnmount)) try {
              d.props = c.memoizedProps, d.state = c.memoizedState, d.componentWillUnmount();
            } catch (h) {
              W(c, b, h);
            }
            Yj(a, b, c);
            break;
          case 21:
            Yj(a, b, c);
            break;
          case 22:
            c.mode & 1 ? (U = (d = U) || null !== c.memoizedState, Yj(a, b, c), U = d) : Yj(a, b, c);
            break;
          default:
            Yj(a, b, c);
        }
      }
      function ak(a) {
        var b = a.updateQueue;
        if (null !== b) {
          a.updateQueue = null;
          var c = a.stateNode;
          null === c && (c = a.stateNode = new Kj());
          b.forEach(function(b2) {
            var d = bk.bind(null, a, b2);
            c.has(b2) || (c.add(b2), b2.then(d, d));
          });
        }
      }
      function ck(a, b) {
        var c = b.deletions;
        if (null !== c) for (var d = 0; d < c.length; d++) {
          var e = c[d];
          try {
            var f = a, g = b, h = g;
            a: for (; null !== h; ) {
              switch (h.tag) {
                case 5:
                  X2 = h.stateNode;
                  Xj = false;
                  break a;
                case 3:
                  X2 = h.stateNode.containerInfo;
                  Xj = true;
                  break a;
                case 4:
                  X2 = h.stateNode.containerInfo;
                  Xj = true;
                  break a;
              }
              h = h.return;
            }
            if (null === X2) throw Error(p(160));
            Zj(f, g, e);
            X2 = null;
            Xj = false;
            var k = e.alternate;
            null !== k && (k.return = null);
            e.return = null;
          } catch (l) {
            W(e, b, l);
          }
        }
        if (b.subtreeFlags & 12854) for (b = b.child; null !== b; ) dk(b, a), b = b.sibling;
      }
      function dk(a, b) {
        var c = a.alternate, d = a.flags;
        switch (a.tag) {
          case 0:
          case 11:
          case 14:
          case 15:
            ck(b, a);
            ek(a);
            if (d & 4) {
              try {
                Pj(3, a, a.return), Qj(3, a);
              } catch (t) {
                W(a, a.return, t);
              }
              try {
                Pj(5, a, a.return);
              } catch (t) {
                W(a, a.return, t);
              }
            }
            break;
          case 1:
            ck(b, a);
            ek(a);
            d & 512 && null !== c && Lj(c, c.return);
            break;
          case 5:
            ck(b, a);
            ek(a);
            d & 512 && null !== c && Lj(c, c.return);
            if (a.flags & 32) {
              var e = a.stateNode;
              try {
                ob(e, "");
              } catch (t) {
                W(a, a.return, t);
              }
            }
            if (d & 4 && (e = a.stateNode, null != e)) {
              var f = a.memoizedProps, g = null !== c ? c.memoizedProps : f, h = a.type, k = a.updateQueue;
              a.updateQueue = null;
              if (null !== k) try {
                "input" === h && "radio" === f.type && null != f.name && ab(e, f);
                vb(h, g);
                var l = vb(h, f);
                for (g = 0; g < k.length; g += 2) {
                  var m = k[g], q = k[g + 1];
                  "style" === m ? sb(e, q) : "dangerouslySetInnerHTML" === m ? nb(e, q) : "children" === m ? ob(e, q) : ta(e, m, q, l);
                }
                switch (h) {
                  case "input":
                    bb(e, f);
                    break;
                  case "textarea":
                    ib(e, f);
                    break;
                  case "select":
                    var r = e._wrapperState.wasMultiple;
                    e._wrapperState.wasMultiple = !!f.multiple;
                    var y = f.value;
                    null != y ? fb(e, !!f.multiple, y, false) : r !== !!f.multiple && (null != f.defaultValue ? fb(
                      e,
                      !!f.multiple,
                      f.defaultValue,
                      true
                    ) : fb(e, !!f.multiple, f.multiple ? [] : "", false));
                }
                e[Pf] = f;
              } catch (t) {
                W(a, a.return, t);
              }
            }
            break;
          case 6:
            ck(b, a);
            ek(a);
            if (d & 4) {
              if (null === a.stateNode) throw Error(p(162));
              e = a.stateNode;
              f = a.memoizedProps;
              try {
                e.nodeValue = f;
              } catch (t) {
                W(a, a.return, t);
              }
            }
            break;
          case 3:
            ck(b, a);
            ek(a);
            if (d & 4 && null !== c && c.memoizedState.isDehydrated) try {
              bd(b.containerInfo);
            } catch (t) {
              W(a, a.return, t);
            }
            break;
          case 4:
            ck(b, a);
            ek(a);
            break;
          case 13:
            ck(b, a);
            ek(a);
            e = a.child;
            e.flags & 8192 && (f = null !== e.memoizedState, e.stateNode.isHidden = f, !f || null !== e.alternate && null !== e.alternate.memoizedState || (fk = B()));
            d & 4 && ak(a);
            break;
          case 22:
            m = null !== c && null !== c.memoizedState;
            a.mode & 1 ? (U = (l = U) || m, ck(b, a), U = l) : ck(b, a);
            ek(a);
            if (d & 8192) {
              l = null !== a.memoizedState;
              if ((a.stateNode.isHidden = l) && !m && 0 !== (a.mode & 1)) for (V = a, m = a.child; null !== m; ) {
                for (q = V = m; null !== V; ) {
                  r = V;
                  y = r.child;
                  switch (r.tag) {
                    case 0:
                    case 11:
                    case 14:
                    case 15:
                      Pj(4, r, r.return);
                      break;
                    case 1:
                      Lj(r, r.return);
                      var n = r.stateNode;
                      if ("function" === typeof n.componentWillUnmount) {
                        d = r;
                        c = r.return;
                        try {
                          b = d, n.props = b.memoizedProps, n.state = b.memoizedState, n.componentWillUnmount();
                        } catch (t) {
                          W(d, c, t);
                        }
                      }
                      break;
                    case 5:
                      Lj(r, r.return);
                      break;
                    case 22:
                      if (null !== r.memoizedState) {
                        gk(q);
                        continue;
                      }
                  }
                  null !== y ? (y.return = r, V = y) : gk(q);
                }
                m = m.sibling;
              }
              a: for (m = null, q = a; ; ) {
                if (5 === q.tag) {
                  if (null === m) {
                    m = q;
                    try {
                      e = q.stateNode, l ? (f = e.style, "function" === typeof f.setProperty ? f.setProperty("display", "none", "important") : f.display = "none") : (h = q.stateNode, k = q.memoizedProps.style, g = void 0 !== k && null !== k && k.hasOwnProperty("display") ? k.display : null, h.style.display = rb("display", g));
                    } catch (t) {
                      W(a, a.return, t);
                    }
                  }
                } else if (6 === q.tag) {
                  if (null === m) try {
                    q.stateNode.nodeValue = l ? "" : q.memoizedProps;
                  } catch (t) {
                    W(a, a.return, t);
                  }
                } else if ((22 !== q.tag && 23 !== q.tag || null === q.memoizedState || q === a) && null !== q.child) {
                  q.child.return = q;
                  q = q.child;
                  continue;
                }
                if (q === a) break a;
                for (; null === q.sibling; ) {
                  if (null === q.return || q.return === a) break a;
                  m === q && (m = null);
                  q = q.return;
                }
                m === q && (m = null);
                q.sibling.return = q.return;
                q = q.sibling;
              }
            }
            break;
          case 19:
            ck(b, a);
            ek(a);
            d & 4 && ak(a);
            break;
          case 21:
            break;
          default:
            ck(
              b,
              a
            ), ek(a);
        }
      }
      function ek(a) {
        var b = a.flags;
        if (b & 2) {
          try {
            a: {
              for (var c = a.return; null !== c; ) {
                if (Tj(c)) {
                  var d = c;
                  break a;
                }
                c = c.return;
              }
              throw Error(p(160));
            }
            switch (d.tag) {
              case 5:
                var e = d.stateNode;
                d.flags & 32 && (ob(e, ""), d.flags &= -33);
                var f = Uj(a);
                Wj(a, f, e);
                break;
              case 3:
              case 4:
                var g = d.stateNode.containerInfo, h = Uj(a);
                Vj(a, h, g);
                break;
              default:
                throw Error(p(161));
            }
          } catch (k) {
            W(a, a.return, k);
          }
          a.flags &= -3;
        }
        b & 4096 && (a.flags &= -4097);
      }
      function hk(a, b, c) {
        V = a;
        ik(a, b, c);
      }
      function ik(a, b, c) {
        for (var d = 0 !== (a.mode & 1); null !== V; ) {
          var e = V, f = e.child;
          if (22 === e.tag && d) {
            var g = null !== e.memoizedState || Jj;
            if (!g) {
              var h = e.alternate, k = null !== h && null !== h.memoizedState || U;
              h = Jj;
              var l = U;
              Jj = g;
              if ((U = k) && !l) for (V = e; null !== V; ) g = V, k = g.child, 22 === g.tag && null !== g.memoizedState ? jk(e) : null !== k ? (k.return = g, V = k) : jk(e);
              for (; null !== f; ) V = f, ik(f, b, c), f = f.sibling;
              V = e;
              Jj = h;
              U = l;
            }
            kk(a, b, c);
          } else 0 !== (e.subtreeFlags & 8772) && null !== f ? (f.return = e, V = f) : kk(a, b, c);
        }
      }
      function kk(a) {
        for (; null !== V; ) {
          var b = V;
          if (0 !== (b.flags & 8772)) {
            var c = b.alternate;
            try {
              if (0 !== (b.flags & 8772)) switch (b.tag) {
                case 0:
                case 11:
                case 15:
                  U || Qj(5, b);
                  break;
                case 1:
                  var d = b.stateNode;
                  if (b.flags & 4 && !U) if (null === c) d.componentDidMount();
                  else {
                    var e = b.elementType === b.type ? c.memoizedProps : Ci(b.type, c.memoizedProps);
                    d.componentDidUpdate(e, c.memoizedState, d.__reactInternalSnapshotBeforeUpdate);
                  }
                  var f = b.updateQueue;
                  null !== f && sh(b, f, d);
                  break;
                case 3:
                  var g = b.updateQueue;
                  if (null !== g) {
                    c = null;
                    if (null !== b.child) switch (b.child.tag) {
                      case 5:
                        c = b.child.stateNode;
                        break;
                      case 1:
                        c = b.child.stateNode;
                    }
                    sh(b, g, c);
                  }
                  break;
                case 5:
                  var h = b.stateNode;
                  if (null === c && b.flags & 4) {
                    c = h;
                    var k = b.memoizedProps;
                    switch (b.type) {
                      case "button":
                      case "input":
                      case "select":
                      case "textarea":
                        k.autoFocus && c.focus();
                        break;
                      case "img":
                        k.src && (c.src = k.src);
                    }
                  }
                  break;
                case 6:
                  break;
                case 4:
                  break;
                case 12:
                  break;
                case 13:
                  if (null === b.memoizedState) {
                    var l = b.alternate;
                    if (null !== l) {
                      var m = l.memoizedState;
                      if (null !== m) {
                        var q = m.dehydrated;
                        null !== q && bd(q);
                      }
                    }
                  }
                  break;
                case 19:
                case 17:
                case 21:
                case 22:
                case 23:
                case 25:
                  break;
                default:
                  throw Error(p(163));
              }
              U || b.flags & 512 && Rj(b);
            } catch (r) {
              W(b, b.return, r);
            }
          }
          if (b === a) {
            V = null;
            break;
          }
          c = b.sibling;
          if (null !== c) {
            c.return = b.return;
            V = c;
            break;
          }
          V = b.return;
        }
      }
      function gk(a) {
        for (; null !== V; ) {
          var b = V;
          if (b === a) {
            V = null;
            break;
          }
          var c = b.sibling;
          if (null !== c) {
            c.return = b.return;
            V = c;
            break;
          }
          V = b.return;
        }
      }
      function jk(a) {
        for (; null !== V; ) {
          var b = V;
          try {
            switch (b.tag) {
              case 0:
              case 11:
              case 15:
                var c = b.return;
                try {
                  Qj(4, b);
                } catch (k) {
                  W(b, c, k);
                }
                break;
              case 1:
                var d = b.stateNode;
                if ("function" === typeof d.componentDidMount) {
                  var e = b.return;
                  try {
                    d.componentDidMount();
                  } catch (k) {
                    W(b, e, k);
                  }
                }
                var f = b.return;
                try {
                  Rj(b);
                } catch (k) {
                  W(b, f, k);
                }
                break;
              case 5:
                var g = b.return;
                try {
                  Rj(b);
                } catch (k) {
                  W(b, g, k);
                }
            }
          } catch (k) {
            W(b, b.return, k);
          }
          if (b === a) {
            V = null;
            break;
          }
          var h = b.sibling;
          if (null !== h) {
            h.return = b.return;
            V = h;
            break;
          }
          V = b.return;
        }
      }
      var lk = Math.ceil;
      var mk = ua.ReactCurrentDispatcher;
      var nk = ua.ReactCurrentOwner;
      var ok = ua.ReactCurrentBatchConfig;
      var K = 0;
      var Q = null;
      var Y = null;
      var Z = 0;
      var fj = 0;
      var ej = Uf(0);
      var T = 0;
      var pk = null;
      var rh = 0;
      var qk = 0;
      var rk = 0;
      var sk = null;
      var tk = null;
      var fk = 0;
      var Gj = Infinity;
      var uk = null;
      var Oi = false;
      var Pi = null;
      var Ri = null;
      var vk = false;
      var wk = null;
      var xk = 0;
      var yk = 0;
      var zk = null;
      var Ak = -1;
      var Bk = 0;
      function R() {
        return 0 !== (K & 6) ? B() : -1 !== Ak ? Ak : Ak = B();
      }
      function yi(a) {
        if (0 === (a.mode & 1)) return 1;
        if (0 !== (K & 2) && 0 !== Z) return Z & -Z;
        if (null !== Kg.transition) return 0 === Bk && (Bk = yc()), Bk;
        a = C;
        if (0 !== a) return a;
        a = window.event;
        a = void 0 === a ? 16 : jd(a.type);
        return a;
      }
      function gi(a, b, c, d) {
        if (50 < yk) throw yk = 0, zk = null, Error(p(185));
        Ac(a, c, d);
        if (0 === (K & 2) || a !== Q) a === Q && (0 === (K & 2) && (qk |= c), 4 === T && Ck(a, Z)), Dk(a, d), 1 === c && 0 === K && 0 === (b.mode & 1) && (Gj = B() + 500, fg && jg());
      }
      function Dk(a, b) {
        var c = a.callbackNode;
        wc(a, b);
        var d = uc(a, a === Q ? Z : 0);
        if (0 === d) null !== c && bc(c), a.callbackNode = null, a.callbackPriority = 0;
        else if (b = d & -d, a.callbackPriority !== b) {
          null != c && bc(c);
          if (1 === b) 0 === a.tag ? ig(Ek.bind(null, a)) : hg(Ek.bind(null, a)), Jf(function() {
            0 === (K & 6) && jg();
          }), c = null;
          else {
            switch (Dc(d)) {
              case 1:
                c = fc;
                break;
              case 4:
                c = gc;
                break;
              case 16:
                c = hc;
                break;
              case 536870912:
                c = jc;
                break;
              default:
                c = hc;
            }
            c = Fk(c, Gk.bind(null, a));
          }
          a.callbackPriority = b;
          a.callbackNode = c;
        }
      }
      function Gk(a, b) {
        Ak = -1;
        Bk = 0;
        if (0 !== (K & 6)) throw Error(p(327));
        var c = a.callbackNode;
        if (Hk() && a.callbackNode !== c) return null;
        var d = uc(a, a === Q ? Z : 0);
        if (0 === d) return null;
        if (0 !== (d & 30) || 0 !== (d & a.expiredLanes) || b) b = Ik(a, d);
        else {
          b = d;
          var e = K;
          K |= 2;
          var f = Jk();
          if (Q !== a || Z !== b) uk = null, Gj = B() + 500, Kk(a, b);
          do
            try {
              Lk();
              break;
            } catch (h) {
              Mk(a, h);
            }
          while (1);
          $g();
          mk.current = f;
          K = e;
          null !== Y ? b = 0 : (Q = null, Z = 0, b = T);
        }
        if (0 !== b) {
          2 === b && (e = xc(a), 0 !== e && (d = e, b = Nk(a, e)));
          if (1 === b) throw c = pk, Kk(a, 0), Ck(a, d), Dk(a, B()), c;
          if (6 === b) Ck(a, d);
          else {
            e = a.current.alternate;
            if (0 === (d & 30) && !Ok(e) && (b = Ik(a, d), 2 === b && (f = xc(a), 0 !== f && (d = f, b = Nk(a, f))), 1 === b)) throw c = pk, Kk(a, 0), Ck(a, d), Dk(a, B()), c;
            a.finishedWork = e;
            a.finishedLanes = d;
            switch (b) {
              case 0:
              case 1:
                throw Error(p(345));
              case 2:
                Pk(a, tk, uk);
                break;
              case 3:
                Ck(a, d);
                if ((d & 130023424) === d && (b = fk + 500 - B(), 10 < b)) {
                  if (0 !== uc(a, 0)) break;
                  e = a.suspendedLanes;
                  if ((e & d) !== d) {
                    R();
                    a.pingedLanes |= a.suspendedLanes & e;
                    break;
                  }
                  a.timeoutHandle = Ff(Pk.bind(null, a, tk, uk), b);
                  break;
                }
                Pk(a, tk, uk);
                break;
              case 4:
                Ck(a, d);
                if ((d & 4194240) === d) break;
                b = a.eventTimes;
                for (e = -1; 0 < d; ) {
                  var g = 31 - oc(d);
                  f = 1 << g;
                  g = b[g];
                  g > e && (e = g);
                  d &= ~f;
                }
                d = e;
                d = B() - d;
                d = (120 > d ? 120 : 480 > d ? 480 : 1080 > d ? 1080 : 1920 > d ? 1920 : 3e3 > d ? 3e3 : 4320 > d ? 4320 : 1960 * lk(d / 1960)) - d;
                if (10 < d) {
                  a.timeoutHandle = Ff(Pk.bind(null, a, tk, uk), d);
                  break;
                }
                Pk(a, tk, uk);
                break;
              case 5:
                Pk(a, tk, uk);
                break;
              default:
                throw Error(p(329));
            }
          }
        }
        Dk(a, B());
        return a.callbackNode === c ? Gk.bind(null, a) : null;
      }
      function Nk(a, b) {
        var c = sk;
        a.current.memoizedState.isDehydrated && (Kk(a, b).flags |= 256);
        a = Ik(a, b);
        2 !== a && (b = tk, tk = c, null !== b && Fj(b));
        return a;
      }
      function Fj(a) {
        null === tk ? tk = a : tk.push.apply(tk, a);
      }
      function Ok(a) {
        for (var b = a; ; ) {
          if (b.flags & 16384) {
            var c = b.updateQueue;
            if (null !== c && (c = c.stores, null !== c)) for (var d = 0; d < c.length; d++) {
              var e = c[d], f = e.getSnapshot;
              e = e.value;
              try {
                if (!He(f(), e)) return false;
              } catch (g) {
                return false;
              }
            }
          }
          c = b.child;
          if (b.subtreeFlags & 16384 && null !== c) c.return = b, b = c;
          else {
            if (b === a) break;
            for (; null === b.sibling; ) {
              if (null === b.return || b.return === a) return true;
              b = b.return;
            }
            b.sibling.return = b.return;
            b = b.sibling;
          }
        }
        return true;
      }
      function Ck(a, b) {
        b &= ~rk;
        b &= ~qk;
        a.suspendedLanes |= b;
        a.pingedLanes &= ~b;
        for (a = a.expirationTimes; 0 < b; ) {
          var c = 31 - oc(b), d = 1 << c;
          a[c] = -1;
          b &= ~d;
        }
      }
      function Ek(a) {
        if (0 !== (K & 6)) throw Error(p(327));
        Hk();
        var b = uc(a, 0);
        if (0 === (b & 1)) return Dk(a, B()), null;
        var c = Ik(a, b);
        if (0 !== a.tag && 2 === c) {
          var d = xc(a);
          0 !== d && (b = d, c = Nk(a, d));
        }
        if (1 === c) throw c = pk, Kk(a, 0), Ck(a, b), Dk(a, B()), c;
        if (6 === c) throw Error(p(345));
        a.finishedWork = a.current.alternate;
        a.finishedLanes = b;
        Pk(a, tk, uk);
        Dk(a, B());
        return null;
      }
      function Qk(a, b) {
        var c = K;
        K |= 1;
        try {
          return a(b);
        } finally {
          K = c, 0 === K && (Gj = B() + 500, fg && jg());
        }
      }
      function Rk(a) {
        null !== wk && 0 === wk.tag && 0 === (K & 6) && Hk();
        var b = K;
        K |= 1;
        var c = ok.transition, d = C;
        try {
          if (ok.transition = null, C = 1, a) return a();
        } finally {
          C = d, ok.transition = c, K = b, 0 === (K & 6) && jg();
        }
      }
      function Hj() {
        fj = ej.current;
        E(ej);
      }
      function Kk(a, b) {
        a.finishedWork = null;
        a.finishedLanes = 0;
        var c = a.timeoutHandle;
        -1 !== c && (a.timeoutHandle = -1, Gf(c));
        if (null !== Y) for (c = Y.return; null !== c; ) {
          var d = c;
          wg(d);
          switch (d.tag) {
            case 1:
              d = d.type.childContextTypes;
              null !== d && void 0 !== d && $f();
              break;
            case 3:
              zh();
              E(Wf);
              E(H);
              Eh();
              break;
            case 5:
              Bh(d);
              break;
            case 4:
              zh();
              break;
            case 13:
              E(L);
              break;
            case 19:
              E(L);
              break;
            case 10:
              ah(d.type._context);
              break;
            case 22:
            case 23:
              Hj();
          }
          c = c.return;
        }
        Q = a;
        Y = a = Pg(a.current, null);
        Z = fj = b;
        T = 0;
        pk = null;
        rk = qk = rh = 0;
        tk = sk = null;
        if (null !== fh) {
          for (b = 0; b < fh.length; b++) if (c = fh[b], d = c.interleaved, null !== d) {
            c.interleaved = null;
            var e = d.next, f = c.pending;
            if (null !== f) {
              var g = f.next;
              f.next = e;
              d.next = g;
            }
            c.pending = d;
          }
          fh = null;
        }
        return a;
      }
      function Mk(a, b) {
        do {
          var c = Y;
          try {
            $g();
            Fh.current = Rh;
            if (Ih) {
              for (var d = M.memoizedState; null !== d; ) {
                var e = d.queue;
                null !== e && (e.pending = null);
                d = d.next;
              }
              Ih = false;
            }
            Hh = 0;
            O = N = M = null;
            Jh = false;
            Kh = 0;
            nk.current = null;
            if (null === c || null === c.return) {
              T = 1;
              pk = b;
              Y = null;
              break;
            }
            a: {
              var f = a, g = c.return, h = c, k = b;
              b = Z;
              h.flags |= 32768;
              if (null !== k && "object" === typeof k && "function" === typeof k.then) {
                var l = k, m = h, q = m.tag;
                if (0 === (m.mode & 1) && (0 === q || 11 === q || 15 === q)) {
                  var r = m.alternate;
                  r ? (m.updateQueue = r.updateQueue, m.memoizedState = r.memoizedState, m.lanes = r.lanes) : (m.updateQueue = null, m.memoizedState = null);
                }
                var y = Ui(g);
                if (null !== y) {
                  y.flags &= -257;
                  Vi(y, g, h, f, b);
                  y.mode & 1 && Si(f, l, b);
                  b = y;
                  k = l;
                  var n = b.updateQueue;
                  if (null === n) {
                    var t = /* @__PURE__ */ new Set();
                    t.add(k);
                    b.updateQueue = t;
                  } else n.add(k);
                  break a;
                } else {
                  if (0 === (b & 1)) {
                    Si(f, l, b);
                    tj();
                    break a;
                  }
                  k = Error(p(426));
                }
              } else if (I && h.mode & 1) {
                var J = Ui(g);
                if (null !== J) {
                  0 === (J.flags & 65536) && (J.flags |= 256);
                  Vi(J, g, h, f, b);
                  Jg(Ji(k, h));
                  break a;
                }
              }
              f = k = Ji(k, h);
              4 !== T && (T = 2);
              null === sk ? sk = [f] : sk.push(f);
              f = g;
              do {
                switch (f.tag) {
                  case 3:
                    f.flags |= 65536;
                    b &= -b;
                    f.lanes |= b;
                    var x = Ni(f, k, b);
                    ph(f, x);
                    break a;
                  case 1:
                    h = k;
                    var w = f.type, u = f.stateNode;
                    if (0 === (f.flags & 128) && ("function" === typeof w.getDerivedStateFromError || null !== u && "function" === typeof u.componentDidCatch && (null === Ri || !Ri.has(u)))) {
                      f.flags |= 65536;
                      b &= -b;
                      f.lanes |= b;
                      var F = Qi(f, h, b);
                      ph(f, F);
                      break a;
                    }
                }
                f = f.return;
              } while (null !== f);
            }
            Sk(c);
          } catch (na) {
            b = na;
            Y === c && null !== c && (Y = c = c.return);
            continue;
          }
          break;
        } while (1);
      }
      function Jk() {
        var a = mk.current;
        mk.current = Rh;
        return null === a ? Rh : a;
      }
      function tj() {
        if (0 === T || 3 === T || 2 === T) T = 4;
        null === Q || 0 === (rh & 268435455) && 0 === (qk & 268435455) || Ck(Q, Z);
      }
      function Ik(a, b) {
        var c = K;
        K |= 2;
        var d = Jk();
        if (Q !== a || Z !== b) uk = null, Kk(a, b);
        do
          try {
            Tk();
            break;
          } catch (e) {
            Mk(a, e);
          }
        while (1);
        $g();
        K = c;
        mk.current = d;
        if (null !== Y) throw Error(p(261));
        Q = null;
        Z = 0;
        return T;
      }
      function Tk() {
        for (; null !== Y; ) Uk(Y);
      }
      function Lk() {
        for (; null !== Y && !cc(); ) Uk(Y);
      }
      function Uk(a) {
        var b = Vk(a.alternate, a, fj);
        a.memoizedProps = a.pendingProps;
        null === b ? Sk(a) : Y = b;
        nk.current = null;
      }
      function Sk(a) {
        var b = a;
        do {
          var c = b.alternate;
          a = b.return;
          if (0 === (b.flags & 32768)) {
            if (c = Ej(c, b, fj), null !== c) {
              Y = c;
              return;
            }
          } else {
            c = Ij(c, b);
            if (null !== c) {
              c.flags &= 32767;
              Y = c;
              return;
            }
            if (null !== a) a.flags |= 32768, a.subtreeFlags = 0, a.deletions = null;
            else {
              T = 6;
              Y = null;
              return;
            }
          }
          b = b.sibling;
          if (null !== b) {
            Y = b;
            return;
          }
          Y = b = a;
        } while (null !== b);
        0 === T && (T = 5);
      }
      function Pk(a, b, c) {
        var d = C, e = ok.transition;
        try {
          ok.transition = null, C = 1, Wk(a, b, c, d);
        } finally {
          ok.transition = e, C = d;
        }
        return null;
      }
      function Wk(a, b, c, d) {
        do
          Hk();
        while (null !== wk);
        if (0 !== (K & 6)) throw Error(p(327));
        c = a.finishedWork;
        var e = a.finishedLanes;
        if (null === c) return null;
        a.finishedWork = null;
        a.finishedLanes = 0;
        if (c === a.current) throw Error(p(177));
        a.callbackNode = null;
        a.callbackPriority = 0;
        var f = c.lanes | c.childLanes;
        Bc(a, f);
        a === Q && (Y = Q = null, Z = 0);
        0 === (c.subtreeFlags & 2064) && 0 === (c.flags & 2064) || vk || (vk = true, Fk(hc, function() {
          Hk();
          return null;
        }));
        f = 0 !== (c.flags & 15990);
        if (0 !== (c.subtreeFlags & 15990) || f) {
          f = ok.transition;
          ok.transition = null;
          var g = C;
          C = 1;
          var h = K;
          K |= 4;
          nk.current = null;
          Oj(a, c);
          dk(c, a);
          Oe(Df);
          dd = !!Cf;
          Df = Cf = null;
          a.current = c;
          hk(c, a, e);
          dc();
          K = h;
          C = g;
          ok.transition = f;
        } else a.current = c;
        vk && (vk = false, wk = a, xk = e);
        f = a.pendingLanes;
        0 === f && (Ri = null);
        mc(c.stateNode, d);
        Dk(a, B());
        if (null !== b) for (d = a.onRecoverableError, c = 0; c < b.length; c++) e = b[c], d(e.value, { componentStack: e.stack, digest: e.digest });
        if (Oi) throw Oi = false, a = Pi, Pi = null, a;
        0 !== (xk & 1) && 0 !== a.tag && Hk();
        f = a.pendingLanes;
        0 !== (f & 1) ? a === zk ? yk++ : (yk = 0, zk = a) : yk = 0;
        jg();
        return null;
      }
      function Hk() {
        if (null !== wk) {
          var a = Dc(xk), b = ok.transition, c = C;
          try {
            ok.transition = null;
            C = 16 > a ? 16 : a;
            if (null === wk) var d = false;
            else {
              a = wk;
              wk = null;
              xk = 0;
              if (0 !== (K & 6)) throw Error(p(331));
              var e = K;
              K |= 4;
              for (V = a.current; null !== V; ) {
                var f = V, g = f.child;
                if (0 !== (V.flags & 16)) {
                  var h = f.deletions;
                  if (null !== h) {
                    for (var k = 0; k < h.length; k++) {
                      var l = h[k];
                      for (V = l; null !== V; ) {
                        var m = V;
                        switch (m.tag) {
                          case 0:
                          case 11:
                          case 15:
                            Pj(8, m, f);
                        }
                        var q = m.child;
                        if (null !== q) q.return = m, V = q;
                        else for (; null !== V; ) {
                          m = V;
                          var r = m.sibling, y = m.return;
                          Sj(m);
                          if (m === l) {
                            V = null;
                            break;
                          }
                          if (null !== r) {
                            r.return = y;
                            V = r;
                            break;
                          }
                          V = y;
                        }
                      }
                    }
                    var n = f.alternate;
                    if (null !== n) {
                      var t = n.child;
                      if (null !== t) {
                        n.child = null;
                        do {
                          var J = t.sibling;
                          t.sibling = null;
                          t = J;
                        } while (null !== t);
                      }
                    }
                    V = f;
                  }
                }
                if (0 !== (f.subtreeFlags & 2064) && null !== g) g.return = f, V = g;
                else b: for (; null !== V; ) {
                  f = V;
                  if (0 !== (f.flags & 2048)) switch (f.tag) {
                    case 0:
                    case 11:
                    case 15:
                      Pj(9, f, f.return);
                  }
                  var x = f.sibling;
                  if (null !== x) {
                    x.return = f.return;
                    V = x;
                    break b;
                  }
                  V = f.return;
                }
              }
              var w = a.current;
              for (V = w; null !== V; ) {
                g = V;
                var u = g.child;
                if (0 !== (g.subtreeFlags & 2064) && null !== u) u.return = g, V = u;
                else b: for (g = w; null !== V; ) {
                  h = V;
                  if (0 !== (h.flags & 2048)) try {
                    switch (h.tag) {
                      case 0:
                      case 11:
                      case 15:
                        Qj(9, h);
                    }
                  } catch (na) {
                    W(h, h.return, na);
                  }
                  if (h === g) {
                    V = null;
                    break b;
                  }
                  var F = h.sibling;
                  if (null !== F) {
                    F.return = h.return;
                    V = F;
                    break b;
                  }
                  V = h.return;
                }
              }
              K = e;
              jg();
              if (lc && "function" === typeof lc.onPostCommitFiberRoot) try {
                lc.onPostCommitFiberRoot(kc, a);
              } catch (na) {
              }
              d = true;
            }
            return d;
          } finally {
            C = c, ok.transition = b;
          }
        }
        return false;
      }
      function Xk(a, b, c) {
        b = Ji(c, b);
        b = Ni(a, b, 1);
        a = nh(a, b, 1);
        b = R();
        null !== a && (Ac(a, 1, b), Dk(a, b));
      }
      function W(a, b, c) {
        if (3 === a.tag) Xk(a, a, c);
        else for (; null !== b; ) {
          if (3 === b.tag) {
            Xk(b, a, c);
            break;
          } else if (1 === b.tag) {
            var d = b.stateNode;
            if ("function" === typeof b.type.getDerivedStateFromError || "function" === typeof d.componentDidCatch && (null === Ri || !Ri.has(d))) {
              a = Ji(c, a);
              a = Qi(b, a, 1);
              b = nh(b, a, 1);
              a = R();
              null !== b && (Ac(b, 1, a), Dk(b, a));
              break;
            }
          }
          b = b.return;
        }
      }
      function Ti(a, b, c) {
        var d = a.pingCache;
        null !== d && d.delete(b);
        b = R();
        a.pingedLanes |= a.suspendedLanes & c;
        Q === a && (Z & c) === c && (4 === T || 3 === T && (Z & 130023424) === Z && 500 > B() - fk ? Kk(a, 0) : rk |= c);
        Dk(a, b);
      }
      function Yk(a, b) {
        0 === b && (0 === (a.mode & 1) ? b = 1 : (b = sc, sc <<= 1, 0 === (sc & 130023424) && (sc = 4194304)));
        var c = R();
        a = ih(a, b);
        null !== a && (Ac(a, b, c), Dk(a, c));
      }
      function uj(a) {
        var b = a.memoizedState, c = 0;
        null !== b && (c = b.retryLane);
        Yk(a, c);
      }
      function bk(a, b) {
        var c = 0;
        switch (a.tag) {
          case 13:
            var d = a.stateNode;
            var e = a.memoizedState;
            null !== e && (c = e.retryLane);
            break;
          case 19:
            d = a.stateNode;
            break;
          default:
            throw Error(p(314));
        }
        null !== d && d.delete(b);
        Yk(a, c);
      }
      var Vk;
      Vk = function(a, b, c) {
        if (null !== a) if (a.memoizedProps !== b.pendingProps || Wf.current) dh = true;
        else {
          if (0 === (a.lanes & c) && 0 === (b.flags & 128)) return dh = false, yj(a, b, c);
          dh = 0 !== (a.flags & 131072) ? true : false;
        }
        else dh = false, I && 0 !== (b.flags & 1048576) && ug(b, ng, b.index);
        b.lanes = 0;
        switch (b.tag) {
          case 2:
            var d = b.type;
            ij(a, b);
            a = b.pendingProps;
            var e = Yf(b, H.current);
            ch(b, c);
            e = Nh(null, b, d, a, e, c);
            var f = Sh();
            b.flags |= 1;
            "object" === typeof e && null !== e && "function" === typeof e.render && void 0 === e.$$typeof ? (b.tag = 1, b.memoizedState = null, b.updateQueue = null, Zf(d) ? (f = true, cg(b)) : f = false, b.memoizedState = null !== e.state && void 0 !== e.state ? e.state : null, kh(b), e.updater = Ei, b.stateNode = e, e._reactInternals = b, Ii(b, d, a, c), b = jj(null, b, d, true, f, c)) : (b.tag = 0, I && f && vg(b), Xi(null, b, e, c), b = b.child);
            return b;
          case 16:
            d = b.elementType;
            a: {
              ij(a, b);
              a = b.pendingProps;
              e = d._init;
              d = e(d._payload);
              b.type = d;
              e = b.tag = Zk(d);
              a = Ci(d, a);
              switch (e) {
                case 0:
                  b = cj(null, b, d, a, c);
                  break a;
                case 1:
                  b = hj(null, b, d, a, c);
                  break a;
                case 11:
                  b = Yi(null, b, d, a, c);
                  break a;
                case 14:
                  b = $i(null, b, d, Ci(d.type, a), c);
                  break a;
              }
              throw Error(p(
                306,
                d,
                ""
              ));
            }
            return b;
          case 0:
            return d = b.type, e = b.pendingProps, e = b.elementType === d ? e : Ci(d, e), cj(a, b, d, e, c);
          case 1:
            return d = b.type, e = b.pendingProps, e = b.elementType === d ? e : Ci(d, e), hj(a, b, d, e, c);
          case 3:
            a: {
              kj(b);
              if (null === a) throw Error(p(387));
              d = b.pendingProps;
              f = b.memoizedState;
              e = f.element;
              lh(a, b);
              qh(b, d, null, c);
              var g = b.memoizedState;
              d = g.element;
              if (f.isDehydrated) if (f = { element: d, isDehydrated: false, cache: g.cache, pendingSuspenseBoundaries: g.pendingSuspenseBoundaries, transitions: g.transitions }, b.updateQueue.baseState = f, b.memoizedState = f, b.flags & 256) {
                e = Ji(Error(p(423)), b);
                b = lj(a, b, d, c, e);
                break a;
              } else if (d !== e) {
                e = Ji(Error(p(424)), b);
                b = lj(a, b, d, c, e);
                break a;
              } else for (yg = Lf(b.stateNode.containerInfo.firstChild), xg = b, I = true, zg = null, c = Vg(b, null, d, c), b.child = c; c; ) c.flags = c.flags & -3 | 4096, c = c.sibling;
              else {
                Ig();
                if (d === e) {
                  b = Zi(a, b, c);
                  break a;
                }
                Xi(a, b, d, c);
              }
              b = b.child;
            }
            return b;
          case 5:
            return Ah(b), null === a && Eg(b), d = b.type, e = b.pendingProps, f = null !== a ? a.memoizedProps : null, g = e.children, Ef(d, e) ? g = null : null !== f && Ef(d, f) && (b.flags |= 32), gj(a, b), Xi(a, b, g, c), b.child;
          case 6:
            return null === a && Eg(b), null;
          case 13:
            return oj(a, b, c);
          case 4:
            return yh(b, b.stateNode.containerInfo), d = b.pendingProps, null === a ? b.child = Ug(b, null, d, c) : Xi(a, b, d, c), b.child;
          case 11:
            return d = b.type, e = b.pendingProps, e = b.elementType === d ? e : Ci(d, e), Yi(a, b, d, e, c);
          case 7:
            return Xi(a, b, b.pendingProps, c), b.child;
          case 8:
            return Xi(a, b, b.pendingProps.children, c), b.child;
          case 12:
            return Xi(a, b, b.pendingProps.children, c), b.child;
          case 10:
            a: {
              d = b.type._context;
              e = b.pendingProps;
              f = b.memoizedProps;
              g = e.value;
              G(Wg, d._currentValue);
              d._currentValue = g;
              if (null !== f) if (He(f.value, g)) {
                if (f.children === e.children && !Wf.current) {
                  b = Zi(a, b, c);
                  break a;
                }
              } else for (f = b.child, null !== f && (f.return = b); null !== f; ) {
                var h = f.dependencies;
                if (null !== h) {
                  g = f.child;
                  for (var k = h.firstContext; null !== k; ) {
                    if (k.context === d) {
                      if (1 === f.tag) {
                        k = mh(-1, c & -c);
                        k.tag = 2;
                        var l = f.updateQueue;
                        if (null !== l) {
                          l = l.shared;
                          var m = l.pending;
                          null === m ? k.next = k : (k.next = m.next, m.next = k);
                          l.pending = k;
                        }
                      }
                      f.lanes |= c;
                      k = f.alternate;
                      null !== k && (k.lanes |= c);
                      bh(
                        f.return,
                        c,
                        b
                      );
                      h.lanes |= c;
                      break;
                    }
                    k = k.next;
                  }
                } else if (10 === f.tag) g = f.type === b.type ? null : f.child;
                else if (18 === f.tag) {
                  g = f.return;
                  if (null === g) throw Error(p(341));
                  g.lanes |= c;
                  h = g.alternate;
                  null !== h && (h.lanes |= c);
                  bh(g, c, b);
                  g = f.sibling;
                } else g = f.child;
                if (null !== g) g.return = f;
                else for (g = f; null !== g; ) {
                  if (g === b) {
                    g = null;
                    break;
                  }
                  f = g.sibling;
                  if (null !== f) {
                    f.return = g.return;
                    g = f;
                    break;
                  }
                  g = g.return;
                }
                f = g;
              }
              Xi(a, b, e.children, c);
              b = b.child;
            }
            return b;
          case 9:
            return e = b.type, d = b.pendingProps.children, ch(b, c), e = eh(e), d = d(e), b.flags |= 1, Xi(a, b, d, c), b.child;
          case 14:
            return d = b.type, e = Ci(d, b.pendingProps), e = Ci(d.type, e), $i(a, b, d, e, c);
          case 15:
            return bj(a, b, b.type, b.pendingProps, c);
          case 17:
            return d = b.type, e = b.pendingProps, e = b.elementType === d ? e : Ci(d, e), ij(a, b), b.tag = 1, Zf(d) ? (a = true, cg(b)) : a = false, ch(b, c), Gi(b, d, e), Ii(b, d, e, c), jj(null, b, d, true, a, c);
          case 19:
            return xj(a, b, c);
          case 22:
            return dj(a, b, c);
        }
        throw Error(p(156, b.tag));
      };
      function Fk(a, b) {
        return ac(a, b);
      }
      function $k(a, b, c, d) {
        this.tag = a;
        this.key = c;
        this.sibling = this.child = this.return = this.stateNode = this.type = this.elementType = null;
        this.index = 0;
        this.ref = null;
        this.pendingProps = b;
        this.dependencies = this.memoizedState = this.updateQueue = this.memoizedProps = null;
        this.mode = d;
        this.subtreeFlags = this.flags = 0;
        this.deletions = null;
        this.childLanes = this.lanes = 0;
        this.alternate = null;
      }
      function Bg(a, b, c, d) {
        return new $k(a, b, c, d);
      }
      function aj(a) {
        a = a.prototype;
        return !(!a || !a.isReactComponent);
      }
      function Zk(a) {
        if ("function" === typeof a) return aj(a) ? 1 : 0;
        if (void 0 !== a && null !== a) {
          a = a.$$typeof;
          if (a === Da) return 11;
          if (a === Ga) return 14;
        }
        return 2;
      }
      function Pg(a, b) {
        var c = a.alternate;
        null === c ? (c = Bg(a.tag, b, a.key, a.mode), c.elementType = a.elementType, c.type = a.type, c.stateNode = a.stateNode, c.alternate = a, a.alternate = c) : (c.pendingProps = b, c.type = a.type, c.flags = 0, c.subtreeFlags = 0, c.deletions = null);
        c.flags = a.flags & 14680064;
        c.childLanes = a.childLanes;
        c.lanes = a.lanes;
        c.child = a.child;
        c.memoizedProps = a.memoizedProps;
        c.memoizedState = a.memoizedState;
        c.updateQueue = a.updateQueue;
        b = a.dependencies;
        c.dependencies = null === b ? null : { lanes: b.lanes, firstContext: b.firstContext };
        c.sibling = a.sibling;
        c.index = a.index;
        c.ref = a.ref;
        return c;
      }
      function Rg(a, b, c, d, e, f) {
        var g = 2;
        d = a;
        if ("function" === typeof a) aj(a) && (g = 1);
        else if ("string" === typeof a) g = 5;
        else a: switch (a) {
          case ya:
            return Tg(c.children, e, f, b);
          case za:
            g = 8;
            e |= 8;
            break;
          case Aa:
            return a = Bg(12, c, b, e | 2), a.elementType = Aa, a.lanes = f, a;
          case Ea:
            return a = Bg(13, c, b, e), a.elementType = Ea, a.lanes = f, a;
          case Fa:
            return a = Bg(19, c, b, e), a.elementType = Fa, a.lanes = f, a;
          case Ia:
            return pj(c, e, f, b);
          default:
            if ("object" === typeof a && null !== a) switch (a.$$typeof) {
              case Ba:
                g = 10;
                break a;
              case Ca:
                g = 9;
                break a;
              case Da:
                g = 11;
                break a;
              case Ga:
                g = 14;
                break a;
              case Ha:
                g = 16;
                d = null;
                break a;
            }
            throw Error(p(130, null == a ? a : typeof a, ""));
        }
        b = Bg(g, c, b, e);
        b.elementType = a;
        b.type = d;
        b.lanes = f;
        return b;
      }
      function Tg(a, b, c, d) {
        a = Bg(7, a, d, b);
        a.lanes = c;
        return a;
      }
      function pj(a, b, c, d) {
        a = Bg(22, a, d, b);
        a.elementType = Ia;
        a.lanes = c;
        a.stateNode = { isHidden: false };
        return a;
      }
      function Qg(a, b, c) {
        a = Bg(6, a, null, b);
        a.lanes = c;
        return a;
      }
      function Sg(a, b, c) {
        b = Bg(4, null !== a.children ? a.children : [], a.key, b);
        b.lanes = c;
        b.stateNode = { containerInfo: a.containerInfo, pendingChildren: null, implementation: a.implementation };
        return b;
      }
      function al(a, b, c, d, e) {
        this.tag = b;
        this.containerInfo = a;
        this.finishedWork = this.pingCache = this.current = this.pendingChildren = null;
        this.timeoutHandle = -1;
        this.callbackNode = this.pendingContext = this.context = null;
        this.callbackPriority = 0;
        this.eventTimes = zc(0);
        this.expirationTimes = zc(-1);
        this.entangledLanes = this.finishedLanes = this.mutableReadLanes = this.expiredLanes = this.pingedLanes = this.suspendedLanes = this.pendingLanes = 0;
        this.entanglements = zc(0);
        this.identifierPrefix = d;
        this.onRecoverableError = e;
        this.mutableSourceEagerHydrationData = null;
      }
      function bl(a, b, c, d, e, f, g, h, k) {
        a = new al(a, b, c, h, k);
        1 === b ? (b = 1, true === f && (b |= 8)) : b = 0;
        f = Bg(3, null, null, b);
        a.current = f;
        f.stateNode = a;
        f.memoizedState = { element: d, isDehydrated: c, cache: null, transitions: null, pendingSuspenseBoundaries: null };
        kh(f);
        return a;
      }
      function cl(a, b, c) {
        var d = 3 < arguments.length && void 0 !== arguments[3] ? arguments[3] : null;
        return { $$typeof: wa, key: null == d ? null : "" + d, children: a, containerInfo: b, implementation: c };
      }
      function dl(a) {
        if (!a) return Vf;
        a = a._reactInternals;
        a: {
          if (Vb(a) !== a || 1 !== a.tag) throw Error(p(170));
          var b = a;
          do {
            switch (b.tag) {
              case 3:
                b = b.stateNode.context;
                break a;
              case 1:
                if (Zf(b.type)) {
                  b = b.stateNode.__reactInternalMemoizedMergedChildContext;
                  break a;
                }
            }
            b = b.return;
          } while (null !== b);
          throw Error(p(171));
        }
        if (1 === a.tag) {
          var c = a.type;
          if (Zf(c)) return bg(a, c, b);
        }
        return b;
      }
      function el(a, b, c, d, e, f, g, h, k) {
        a = bl(c, d, true, a, e, f, g, h, k);
        a.context = dl(null);
        c = a.current;
        d = R();
        e = yi(c);
        f = mh(d, e);
        f.callback = void 0 !== b && null !== b ? b : null;
        nh(c, f, e);
        a.current.lanes = e;
        Ac(a, e, d);
        Dk(a, d);
        return a;
      }
      function fl(a, b, c, d) {
        var e = b.current, f = R(), g = yi(e);
        c = dl(c);
        null === b.context ? b.context = c : b.pendingContext = c;
        b = mh(f, g);
        b.payload = { element: a };
        d = void 0 === d ? null : d;
        null !== d && (b.callback = d);
        a = nh(e, b, g);
        null !== a && (gi(a, e, g, f), oh(a, e, g));
        return g;
      }
      function gl(a) {
        a = a.current;
        if (!a.child) return null;
        switch (a.child.tag) {
          case 5:
            return a.child.stateNode;
          default:
            return a.child.stateNode;
        }
      }
      function hl(a, b) {
        a = a.memoizedState;
        if (null !== a && null !== a.dehydrated) {
          var c = a.retryLane;
          a.retryLane = 0 !== c && c < b ? c : b;
        }
      }
      function il(a, b) {
        hl(a, b);
        (a = a.alternate) && hl(a, b);
      }
      function jl() {
        return null;
      }
      var kl = "function" === typeof reportError ? reportError : function(a) {
        console.error(a);
      };
      function ll(a) {
        this._internalRoot = a;
      }
      ml.prototype.render = ll.prototype.render = function(a) {
        var b = this._internalRoot;
        if (null === b) throw Error(p(409));
        fl(a, b, null, null);
      };
      ml.prototype.unmount = ll.prototype.unmount = function() {
        var a = this._internalRoot;
        if (null !== a) {
          this._internalRoot = null;
          var b = a.containerInfo;
          Rk(function() {
            fl(null, a, null, null);
          });
          b[uf] = null;
        }
      };
      function ml(a) {
        this._internalRoot = a;
      }
      ml.prototype.unstable_scheduleHydration = function(a) {
        if (a) {
          var b = Hc();
          a = { blockedOn: null, target: a, priority: b };
          for (var c = 0; c < Qc.length && 0 !== b && b < Qc[c].priority; c++) ;
          Qc.splice(c, 0, a);
          0 === c && Vc(a);
        }
      };
      function nl(a) {
        return !(!a || 1 !== a.nodeType && 9 !== a.nodeType && 11 !== a.nodeType);
      }
      function ol(a) {
        return !(!a || 1 !== a.nodeType && 9 !== a.nodeType && 11 !== a.nodeType && (8 !== a.nodeType || " react-mount-point-unstable " !== a.nodeValue));
      }
      function pl() {
      }
      function ql(a, b, c, d, e) {
        if (e) {
          if ("function" === typeof d) {
            var f = d;
            d = function() {
              var a2 = gl(g);
              f.call(a2);
            };
          }
          var g = el(b, d, a, 0, null, false, false, "", pl);
          a._reactRootContainer = g;
          a[uf] = g.current;
          sf(8 === a.nodeType ? a.parentNode : a);
          Rk();
          return g;
        }
        for (; e = a.lastChild; ) a.removeChild(e);
        if ("function" === typeof d) {
          var h = d;
          d = function() {
            var a2 = gl(k);
            h.call(a2);
          };
        }
        var k = bl(a, 0, false, null, null, false, false, "", pl);
        a._reactRootContainer = k;
        a[uf] = k.current;
        sf(8 === a.nodeType ? a.parentNode : a);
        Rk(function() {
          fl(b, k, c, d);
        });
        return k;
      }
      function rl(a, b, c, d, e) {
        var f = c._reactRootContainer;
        if (f) {
          var g = f;
          if ("function" === typeof e) {
            var h = e;
            e = function() {
              var a2 = gl(g);
              h.call(a2);
            };
          }
          fl(b, g, a, e);
        } else g = ql(c, b, a, e, d);
        return gl(g);
      }
      Ec = function(a) {
        switch (a.tag) {
          case 3:
            var b = a.stateNode;
            if (b.current.memoizedState.isDehydrated) {
              var c = tc(b.pendingLanes);
              0 !== c && (Cc(b, c | 1), Dk(b, B()), 0 === (K & 6) && (Gj = B() + 500, jg()));
            }
            break;
          case 13:
            Rk(function() {
              var b2 = ih(a, 1);
              if (null !== b2) {
                var c2 = R();
                gi(b2, a, 1, c2);
              }
            }), il(a, 1);
        }
      };
      Fc = function(a) {
        if (13 === a.tag) {
          var b = ih(a, 134217728);
          if (null !== b) {
            var c = R();
            gi(b, a, 134217728, c);
          }
          il(a, 134217728);
        }
      };
      Gc = function(a) {
        if (13 === a.tag) {
          var b = yi(a), c = ih(a, b);
          if (null !== c) {
            var d = R();
            gi(c, a, b, d);
          }
          il(a, b);
        }
      };
      Hc = function() {
        return C;
      };
      Ic = function(a, b) {
        var c = C;
        try {
          return C = a, b();
        } finally {
          C = c;
        }
      };
      yb = function(a, b, c) {
        switch (b) {
          case "input":
            bb(a, c);
            b = c.name;
            if ("radio" === c.type && null != b) {
              for (c = a; c.parentNode; ) c = c.parentNode;
              c = c.querySelectorAll("input[name=" + JSON.stringify("" + b) + '][type="radio"]');
              for (b = 0; b < c.length; b++) {
                var d = c[b];
                if (d !== a && d.form === a.form) {
                  var e = Db(d);
                  if (!e) throw Error(p(90));
                  Wa(d);
                  bb(d, e);
                }
              }
            }
            break;
          case "textarea":
            ib(a, c);
            break;
          case "select":
            b = c.value, null != b && fb(a, !!c.multiple, b, false);
        }
      };
      Gb = Qk;
      Hb = Rk;
      var sl = { usingClientEntryPoint: false, Events: [Cb, ue, Db, Eb, Fb, Qk] };
      var tl = { findFiberByHostInstance: Wc, bundleType: 0, version: "18.3.1", rendererPackageName: "react-dom" };
      var ul = { bundleType: tl.bundleType, version: tl.version, rendererPackageName: tl.rendererPackageName, rendererConfig: tl.rendererConfig, overrideHookState: null, overrideHookStateDeletePath: null, overrideHookStateRenamePath: null, overrideProps: null, overridePropsDeletePath: null, overridePropsRenamePath: null, setErrorHandler: null, setSuspenseHandler: null, scheduleUpdate: null, currentDispatcherRef: ua.ReactCurrentDispatcher, findHostInstanceByFiber: function(a) {
        a = Zb(a);
        return null === a ? null : a.stateNode;
      }, findFiberByHostInstance: tl.findFiberByHostInstance || jl, findHostInstancesForRefresh: null, scheduleRefresh: null, scheduleRoot: null, setRefreshHandler: null, getCurrentFiber: null, reconcilerVersion: "18.3.1-next-f1338f8080-20240426" };
      if ("undefined" !== typeof __REACT_DEVTOOLS_GLOBAL_HOOK__) {
        vl = __REACT_DEVTOOLS_GLOBAL_HOOK__;
        if (!vl.isDisabled && vl.supportsFiber) try {
          kc = vl.inject(ul), lc = vl;
        } catch (a) {
        }
      }
      var vl;
      exports.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED = sl;
      exports.createPortal = function(a, b) {
        var c = 2 < arguments.length && void 0 !== arguments[2] ? arguments[2] : null;
        if (!nl(b)) throw Error(p(200));
        return cl(a, b, null, c);
      };
      exports.createRoot = function(a, b) {
        if (!nl(a)) throw Error(p(299));
        var c = false, d = "", e = kl;
        null !== b && void 0 !== b && (true === b.unstable_strictMode && (c = true), void 0 !== b.identifierPrefix && (d = b.identifierPrefix), void 0 !== b.onRecoverableError && (e = b.onRecoverableError));
        b = bl(a, 1, false, null, null, c, false, d, e);
        a[uf] = b.current;
        sf(8 === a.nodeType ? a.parentNode : a);
        return new ll(b);
      };
      exports.findDOMNode = function(a) {
        if (null == a) return null;
        if (1 === a.nodeType) return a;
        var b = a._reactInternals;
        if (void 0 === b) {
          if ("function" === typeof a.render) throw Error(p(188));
          a = Object.keys(a).join(",");
          throw Error(p(268, a));
        }
        a = Zb(b);
        a = null === a ? null : a.stateNode;
        return a;
      };
      exports.flushSync = function(a) {
        return Rk(a);
      };
      exports.hydrate = function(a, b, c) {
        if (!ol(b)) throw Error(p(200));
        return rl(null, a, b, true, c);
      };
      exports.hydrateRoot = function(a, b, c) {
        if (!nl(a)) throw Error(p(405));
        var d = null != c && c.hydratedSources || null, e = false, f = "", g = kl;
        null !== c && void 0 !== c && (true === c.unstable_strictMode && (e = true), void 0 !== c.identifierPrefix && (f = c.identifierPrefix), void 0 !== c.onRecoverableError && (g = c.onRecoverableError));
        b = el(b, null, a, 1, null != c ? c : null, e, false, f, g);
        a[uf] = b.current;
        sf(a);
        if (d) for (a = 0; a < d.length; a++) c = d[a], e = c._getVersion, e = e(c._source), null == b.mutableSourceEagerHydrationData ? b.mutableSourceEagerHydrationData = [c, e] : b.mutableSourceEagerHydrationData.push(
          c,
          e
        );
        return new ml(b);
      };
      exports.render = function(a, b, c) {
        if (!ol(b)) throw Error(p(200));
        return rl(null, a, b, false, c);
      };
      exports.unmountComponentAtNode = function(a) {
        if (!ol(a)) throw Error(p(40));
        return a._reactRootContainer ? (Rk(function() {
          rl(null, null, a, false, function() {
            a._reactRootContainer = null;
            a[uf] = null;
          });
        }), true) : false;
      };
      exports.unstable_batchedUpdates = Qk;
      exports.unstable_renderSubtreeIntoContainer = function(a, b, c, d) {
        if (!ol(c)) throw Error(p(200));
        if (null == a || void 0 === a._reactInternals) throw Error(p(38));
        return rl(a, b, c, false, d);
      };
      exports.version = "18.3.1-next-f1338f8080-20240426";
    }
  });

  // web/console/node_modules/react-dom/index.js
  var require_react_dom = __commonJS({
    "web/console/node_modules/react-dom/index.js"(exports, module) {
      "use strict";
      function checkDCE() {
        if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ === "undefined" || typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE !== "function") {
          return;
        }
        if (false) {
          throw new Error("^_^");
        }
        try {
          __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(checkDCE);
        } catch (err) {
          console.error(err);
        }
      }
      if (true) {
        checkDCE();
        module.exports = require_react_dom_production_min();
      } else {
        module.exports = null;
      }
    }
  });

  // web/console/node_modules/react-dom/client.js
  var require_client = __commonJS({
    "web/console/node_modules/react-dom/client.js"(exports) {
      "use strict";
      var m = require_react_dom();
      if (true) {
        exports.createRoot = m.createRoot;
        exports.hydrateRoot = m.hydrateRoot;
      } else {
        i = m.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED;
        exports.createRoot = function(c, o) {
          i.usingClientEntryPoint = true;
          try {
            return m.createRoot(c, o);
          } finally {
            i.usingClientEntryPoint = false;
          }
        };
        exports.hydrateRoot = function(c, h, o) {
          i.usingClientEntryPoint = true;
          try {
            return m.hydrateRoot(c, h, o);
          } finally {
            i.usingClientEntryPoint = false;
          }
        };
      }
      var i;
    }
  });

  // web/console/node_modules/react/cjs/react-jsx-runtime.production.min.js
  var require_react_jsx_runtime_production_min = __commonJS({
    "web/console/node_modules/react/cjs/react-jsx-runtime.production.min.js"(exports) {
      "use strict";
      var f = require_react();
      var k = Symbol.for("react.element");
      var l = Symbol.for("react.fragment");
      var m = Object.prototype.hasOwnProperty;
      var n = f.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner;
      var p = { key: true, ref: true, __self: true, __source: true };
      function q(c, a, g) {
        var b, d = {}, e = null, h = null;
        void 0 !== g && (e = "" + g);
        void 0 !== a.key && (e = "" + a.key);
        void 0 !== a.ref && (h = a.ref);
        for (b in a) m.call(a, b) && !p.hasOwnProperty(b) && (d[b] = a[b]);
        if (c && c.defaultProps) for (b in a = c.defaultProps, a) void 0 === d[b] && (d[b] = a[b]);
        return { $$typeof: k, type: c, key: e, ref: h, props: d, _owner: n.current };
      }
      exports.Fragment = l;
      exports.jsx = q;
      exports.jsxs = q;
    }
  });

  // web/console/node_modules/react/jsx-runtime.js
  var require_jsx_runtime = __commonJS({
    "web/console/node_modules/react/jsx-runtime.js"(exports, module) {
      "use strict";
      if (true) {
        module.exports = require_react_jsx_runtime_production_min();
      } else {
        module.exports = null;
      }
    }
  });

  // web/console/main.tsx
  var import_react4 = __toESM(require_react());
  var import_client = __toESM(require_client());

  // web/console/cuberelay_v4.tsx
  var import_react3 = __toESM(require_react());

  // web/console/node_modules/lucide-react/dist/esm/createLucideIcon.js
  var import_react2 = __toESM(require_react());

  // web/console/node_modules/lucide-react/dist/esm/shared/src/utils.js
  var toKebabCase = (string) => string.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
  var mergeClasses = (...classes) => classes.filter((className, index, array) => {
    return Boolean(className) && className.trim() !== "" && array.indexOf(className) === index;
  }).join(" ").trim();

  // web/console/node_modules/lucide-react/dist/esm/Icon.js
  var import_react = __toESM(require_react());

  // web/console/node_modules/lucide-react/dist/esm/defaultAttributes.js
  var defaultAttributes = {
    xmlns: "http://www.w3.org/2000/svg",
    width: 24,
    height: 24,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round",
    strokeLinejoin: "round"
  };

  // web/console/node_modules/lucide-react/dist/esm/Icon.js
  var Icon = (0, import_react.forwardRef)(
    ({
      color = "currentColor",
      size = 24,
      strokeWidth = 2,
      absoluteStrokeWidth,
      className = "",
      children,
      iconNode,
      ...rest
    }, ref) => {
      return (0, import_react.createElement)(
        "svg",
        {
          ref,
          ...defaultAttributes,
          width: size,
          height: size,
          stroke: color,
          strokeWidth: absoluteStrokeWidth ? Number(strokeWidth) * 24 / Number(size) : strokeWidth,
          className: mergeClasses("lucide", className),
          ...rest
        },
        [
          ...iconNode.map(([tag, attrs]) => (0, import_react.createElement)(tag, attrs)),
          ...Array.isArray(children) ? children : [children]
        ]
      );
    }
  );

  // web/console/node_modules/lucide-react/dist/esm/createLucideIcon.js
  var createLucideIcon = (iconName, iconNode) => {
    const Component = (0, import_react2.forwardRef)(
      ({ className, ...props }, ref) => (0, import_react2.createElement)(Icon, {
        ref,
        iconNode,
        className: mergeClasses(`lucide-${toKebabCase(iconName)}`, className),
        ...props
      })
    );
    Component.displayName = `${iconName}`;
    return Component;
  };

  // web/console/node_modules/lucide-react/dist/esm/icons/activity.js
  var Activity = createLucideIcon("Activity", [
    [
      "path",
      {
        d: "M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2",
        key: "169zse"
      }
    ]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/bot.js
  var Bot = createLucideIcon("Bot", [
    ["path", { d: "M12 8V4H8", key: "hb8ula" }],
    ["rect", { width: "16", height: "12", x: "4", y: "8", rx: "2", key: "enze0r" }],
    ["path", { d: "M2 14h2", key: "vft8re" }],
    ["path", { d: "M20 14h2", key: "4cs60a" }],
    ["path", { d: "M15 13v2", key: "1xurst" }],
    ["path", { d: "M9 13v2", key: "rq6x2g" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/camera.js
  var Camera = createLucideIcon("Camera", [
    [
      "path",
      {
        d: "M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z",
        key: "1tc9qg"
      }
    ],
    ["circle", { cx: "12", cy: "13", r: "3", key: "1vg3eu" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/chevron-down.js
  var ChevronDown = createLucideIcon("ChevronDown", [
    ["path", { d: "m6 9 6 6 6-6", key: "qrunsl" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/chevron-right.js
  var ChevronRight = createLucideIcon("ChevronRight", [
    ["path", { d: "m9 18 6-6-6-6", key: "mthhwq" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/circle-check.js
  var CircleCheck = createLucideIcon("CircleCheck", [
    ["circle", { cx: "12", cy: "12", r: "10", key: "1mglay" }],
    ["path", { d: "m9 12 2 2 4-4", key: "dzmm74" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/circle-x.js
  var CircleX = createLucideIcon("CircleX", [
    ["circle", { cx: "12", cy: "12", r: "10", key: "1mglay" }],
    ["path", { d: "m15 9-6 6", key: "1uzhvr" }],
    ["path", { d: "m9 9 6 6", key: "z0biqf" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/clock.js
  var Clock = createLucideIcon("Clock", [
    ["circle", { cx: "12", cy: "12", r: "10", key: "1mglay" }],
    ["polyline", { points: "12 6 12 12 16 14", key: "68esgv" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/cpu.js
  var Cpu = createLucideIcon("Cpu", [
    ["rect", { width: "16", height: "16", x: "4", y: "4", rx: "2", key: "14l7u7" }],
    ["rect", { width: "6", height: "6", x: "9", y: "9", rx: "1", key: "5aljv4" }],
    ["path", { d: "M15 2v2", key: "13l42r" }],
    ["path", { d: "M15 20v2", key: "15mkzm" }],
    ["path", { d: "M2 15h2", key: "1gxd5l" }],
    ["path", { d: "M2 9h2", key: "1bbxkp" }],
    ["path", { d: "M20 15h2", key: "19e6y8" }],
    ["path", { d: "M20 9h2", key: "19tzq7" }],
    ["path", { d: "M9 2v2", key: "165o2o" }],
    ["path", { d: "M9 20v2", key: "i2bqo8" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/database.js
  var Database = createLucideIcon("Database", [
    ["ellipse", { cx: "12", cy: "5", rx: "9", ry: "3", key: "msslwz" }],
    ["path", { d: "M3 5V19A9 3 0 0 0 21 19V5", key: "1wlel7" }],
    ["path", { d: "M3 12A9 3 0 0 0 21 12", key: "mv7ke4" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/download.js
  var Download = createLucideIcon("Download", [
    ["path", { d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", key: "ih7n3h" }],
    ["polyline", { points: "7 10 12 15 17 10", key: "2ggqvy" }],
    ["line", { x1: "12", x2: "12", y1: "15", y2: "3", key: "1vk2je" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/file-code-2.js
  var FileCode2 = createLucideIcon("FileCode2", [
    ["path", { d: "M4 22h14a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v4", key: "1pf5j1" }],
    ["path", { d: "M14 2v4a2 2 0 0 0 2 2h4", key: "tnqrlb" }],
    ["path", { d: "m5 12-3 3 3 3", key: "oke12k" }],
    ["path", { d: "m9 18 3-3-3-3", key: "112psh" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/film.js
  var Film = createLucideIcon("Film", [
    ["rect", { width: "18", height: "18", x: "3", y: "3", rx: "2", key: "afitv7" }],
    ["path", { d: "M7 3v18", key: "bbkbws" }],
    ["path", { d: "M3 7.5h4", key: "zfgn84" }],
    ["path", { d: "M3 12h18", key: "1i2n21" }],
    ["path", { d: "M3 16.5h4", key: "1230mu" }],
    ["path", { d: "M17 3v18", key: "in4fa5" }],
    ["path", { d: "M17 7.5h4", key: "myr1c1" }],
    ["path", { d: "M17 16.5h4", key: "go4c1d" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/folder-open.js
  var FolderOpen = createLucideIcon("FolderOpen", [
    [
      "path",
      {
        d: "m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2",
        key: "usdka0"
      }
    ]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/git-branch.js
  var GitBranch = createLucideIcon("GitBranch", [
    ["line", { x1: "6", x2: "6", y1: "3", y2: "15", key: "17qcm7" }],
    ["circle", { cx: "18", cy: "6", r: "3", key: "1h7g24" }],
    ["circle", { cx: "6", cy: "18", r: "3", key: "fqmcym" }],
    ["path", { d: "M18 9a9 9 0 0 1-9 9", key: "n2h4wq" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/grid-3x3.js
  var Grid3x3 = createLucideIcon("Grid3x3", [
    ["rect", { width: "18", height: "18", x: "3", y: "3", rx: "2", key: "afitv7" }],
    ["path", { d: "M3 9h18", key: "1pudct" }],
    ["path", { d: "M3 15h18", key: "5xshup" }],
    ["path", { d: "M9 3v18", key: "fh3hqa" }],
    ["path", { d: "M15 3v18", key: "14nvp0" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/history.js
  var History = createLucideIcon("History", [
    ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
    ["path", { d: "M3 3v5h5", key: "1xhq8a" }],
    ["path", { d: "M12 7v5l4 2", key: "1fdv2h" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/layers.js
  var Layers = createLucideIcon("Layers", [
    [
      "path",
      {
        d: "M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z",
        key: "zw3jo"
      }
    ],
    [
      "path",
      {
        d: "M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12",
        key: "1wduqc"
      }
    ],
    [
      "path",
      {
        d: "M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17",
        key: "kqbvx6"
      }
    ]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/lock.js
  var Lock = createLucideIcon("Lock", [
    ["rect", { width: "18", height: "11", x: "3", y: "11", rx: "2", ry: "2", key: "1w4ew1" }],
    ["path", { d: "M7 11V7a5 5 0 0 1 10 0v4", key: "fwvmzm" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/monitor.js
  var Monitor = createLucideIcon("Monitor", [
    ["rect", { width: "20", height: "14", x: "2", y: "3", rx: "2", key: "48i651" }],
    ["line", { x1: "8", x2: "16", y1: "21", y2: "21", key: "1svkeh" }],
    ["line", { x1: "12", x2: "12", y1: "17", y2: "21", key: "vw1qmm" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/play.js
  var Play = createLucideIcon("Play", [
    ["polygon", { points: "6 3 20 12 6 21 6 3", key: "1oa8hb" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/radio.js
  var Radio = createLucideIcon("Radio", [
    ["path", { d: "M4.9 19.1C1 15.2 1 8.8 4.9 4.9", key: "1vaf9d" }],
    ["path", { d: "M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5", key: "u1ii0m" }],
    ["circle", { cx: "12", cy: "12", r: "2", key: "1c9p78" }],
    ["path", { d: "M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5", key: "1j5fej" }],
    ["path", { d: "M19.1 4.9C23 8.8 23 15.1 19.1 19", key: "10b0cb" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/refresh-cw.js
  var RefreshCw = createLucideIcon("RefreshCw", [
    ["path", { d: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8", key: "v9h5vc" }],
    ["path", { d: "M21 3v5h-5", key: "1q7to0" }],
    ["path", { d: "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16", key: "3uifl3" }],
    ["path", { d: "M8 16H3v5", key: "1cv678" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/rotate-ccw.js
  var RotateCcw = createLucideIcon("RotateCcw", [
    ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
    ["path", { d: "M3 3v5h5", key: "1xhq8a" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/scan.js
  var Scan = createLucideIcon("Scan", [
    ["path", { d: "M3 7V5a2 2 0 0 1 2-2h2", key: "aa7l1z" }],
    ["path", { d: "M17 3h2a2 2 0 0 1 2 2v2", key: "4qcy5o" }],
    ["path", { d: "M21 17v2a2 2 0 0 1-2 2h-2", key: "6vwrx8" }],
    ["path", { d: "M7 21H5a2 2 0 0 1-2-2v-2", key: "ioqczr" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/settings.js
  var Settings = createLucideIcon("Settings", [
    [
      "path",
      {
        d: "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z",
        key: "1qme2f"
      }
    ],
    ["circle", { cx: "12", cy: "12", r: "3", key: "1v7zrd" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/shield-alert.js
  var ShieldAlert = createLucideIcon("ShieldAlert", [
    [
      "path",
      {
        d: "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z",
        key: "oel41y"
      }
    ],
    ["path", { d: "M12 8v4", key: "1got3b" }],
    ["path", { d: "M12 16h.01", key: "1drbdi" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/shield-check.js
  var ShieldCheck = createLucideIcon("ShieldCheck", [
    [
      "path",
      {
        d: "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z",
        key: "oel41y"
      }
    ],
    ["path", { d: "m9 12 2 2 4-4", key: "dzmm74" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/square.js
  var Square = createLucideIcon("Square", [
    ["rect", { width: "18", height: "18", x: "3", y: "3", rx: "2", key: "afitv7" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/triangle-alert.js
  var TriangleAlert = createLucideIcon("TriangleAlert", [
    [
      "path",
      {
        d: "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3",
        key: "wmoenq"
      }
    ],
    ["path", { d: "M12 9v4", key: "juzpu7" }],
    ["path", { d: "M12 17h.01", key: "p32p05" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/upload.js
  var Upload = createLucideIcon("Upload", [
    ["path", { d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", key: "ih7n3h" }],
    ["polyline", { points: "17 8 12 3 7 8", key: "t8dd8p" }],
    ["line", { x1: "12", x2: "12", y1: "3", y2: "15", key: "widbto" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/wifi-off.js
  var WifiOff = createLucideIcon("WifiOff", [
    ["path", { d: "M12 20h.01", key: "zekei9" }],
    ["path", { d: "M8.5 16.429a5 5 0 0 1 7 0", key: "1bycff" }],
    ["path", { d: "M5 12.859a10 10 0 0 1 5.17-2.69", key: "1dl1wf" }],
    ["path", { d: "M19 12.859a10 10 0 0 0-2.007-1.523", key: "4k23kn" }],
    ["path", { d: "M2 8.82a15 15 0 0 1 4.177-2.643", key: "1grhjp" }],
    ["path", { d: "M22 8.82a15 15 0 0 0-11.288-3.764", key: "z3jwby" }],
    ["path", { d: "m2 2 20 20", key: "1ooewy" }]
  ]);

  // web/console/node_modules/lucide-react/dist/esm/icons/x.js
  var X = createLucideIcon("X", [
    ["path", { d: "M18 6 6 18", key: "1bl5f8" }],
    ["path", { d: "m6 6 12 12", key: "d8bk6v" }]
  ]);

  // web/console/cuberelay_v4.tsx
  var import_jsx_runtime = __toESM(require_jsx_runtime());
  var FACE_ORDER = ["U", "R", "F", "D", "L", "B"];
  var MISSION_OPTIONS = [
    {
      type: "INSPECT_CUBE",
      label: "\u516D\u9762\u626B\u63CF",
      shortDesc: "\u4E3B\u52A8\u611F\u77E5\u5E76\u8F93\u51FA 54 \u683C\u5408\u6CD5\u6027\u6821\u9A8C\uFF08\u4E0D\u8F6C\u9762\uFF09",
      capabilityNote: "\u5DF2\u5B9E\u73B0 \xB7 \u4EC5\u8C03\u7528 RGB-D \u5B9A\u4F4D\u3001\u591A\u89C6\u89D2\u626B\u63CF\u4E0E\u72B6\u6001\u6821\u9A8C"
    },
    {
      type: "VERIFY_PHYSICAL_U_TURN",
      label: "U \u5C42\u7269\u7406\u8F6C\u52A8\u9A8C\u8BC1",
      shortDesc: "M3-B \u57FA\u7EBF\uFF1A\u626B\u63CF + \u642C\u8FD0 + \u63A5\u89E6\u62E7 U + 21 \u683C\u590D\u6838",
      capabilityNote: "\u5DF2\u5B9E\u73B0 \xB7 \u4EC5\u652F\u6301\u5355\u6B21\u987A\u65F6\u9488 U (+90\xB0) \u63A5\u89E6\u9A71\u52A8"
    },
    {
      type: "SOLVE_CUBE",
      label: "\u9B54\u65B9\u5B8C\u6574\u6C42\u89E3",
      shortDesc: "\u626B\u63CF + Kociemba \u6C42\u89E3 + \u7269\u7406\u80FD\u529B\u8FB9\u754C\u6838\u67E5",
      capabilityNote: "\u53D7\u80FD\u529B\u9650\u5236 \xB7 \u82E5\u542B R/F/L/B/D/U'/U2 \u5C06\u89E6\u53D1 CAPABILITY_BLOCKED"
    },
    {
      type: "RELAY_SOLVE_CUBE",
      label: "\u4EBA\u673A\u63A5\u529B\u590D\u539F",
      shortDesc: "Gemini Agent \u5168\u81EA\u4E3B\u63A5\u529B + 26-Cubie \u7269\u7406\u6C42\u89E3",
      capabilityNote: "\u5168\u81EA\u4E3B\u95ED\u73AF \xB7 1s\u5FEB\u7784/25s\u7FFB\u626B\u6743\u8861 \xB7 18\u52A8\u4F5C\u81EA\u7531\u76D8 + \u81EA\u7136\u8BED\u8A00\u5951\u7EA6\u534F\u540C"
    }
  ];
  var COLOR_MAP = {
    W: { bg: "#F1F5F9", border: "#CBD5E1", text: "#0F172A", label: "\u767D W" },
    Y: { bg: "#FACC15", border: "#EAB308", text: "#0F172A", label: "\u9EC4 Y" },
    G: { bg: "#22C55E", border: "#16A34A", text: "#052E16", label: "\u7EFF G" },
    B: { bg: "#3B82F6", border: "#2563EB", text: "#EFF6FF", label: "\u84DD B" },
    O: { bg: "#F97316", border: "#EA580C", text: "#FFF7ED", label: "\u6A59 O" },
    R: { bg: "#EF4444", border: "#DC2626", text: "#FEF2F2", label: "\u7EA2 R" },
    UNKNOWN: { bg: "#182338", border: "#334155", text: "#94A3B8", label: "\u672A\u77E5 ?" }
  };
  var CAMERA_PRESETS = [
    { id: "cube_closeup", label: "\u9B54\u65B9\u7279\u5199", desc: "26-Cubie \u9B54\u65B9\u8DDF\u62CD\u7279\u5199\uFF08\u63A8\u8350\uFF09", az: 132, el: -28, dist: 0.28 },
    { id: "gripper_closeup", label: "\u5939\u722A\u7279\u5199", desc: "\u672B\u7AEF\u53CC\u6307\u5939\u6301\u63A5\u89E6\u5C40\u90E8\u673A\u4F4D", az: 146, el: -22, dist: 0.36 },
    { id: "overview", label: "\u573A\u666F\u603B\u89C8", desc: "3/4 \u5B9E\u9A8C\u5BA4\u5DE5\u4F5C\u7AD9\u5168\u5C40\u673A\u4F4D", az: 135, el: -28, dist: 1.15 },
    { id: "top_ortho", label: "\u4FEF\u89C6\u76F8\u673A", desc: "\u9F99\u95E8\u67B6 XY \u5E73\u9762\u6B63\u4EA4\u4FEF\u89C6", az: 90, el: -86, dist: 0.95 }
  ];
  var SAMPLE_PREDICTED_COLORS = [
    "W",
    "R",
    "G",
    "B",
    "W",
    "Y",
    "O",
    "W",
    "B",
    "R",
    "B",
    "Y",
    "G",
    "R",
    "W",
    "O",
    "R",
    "B",
    "G",
    "Y",
    "R",
    "W",
    "G",
    "O",
    "B",
    "G",
    "Y",
    "Y",
    "W",
    "O",
    "R",
    "Y",
    "G",
    "W",
    "B",
    "Y",
    "O",
    "G",
    "W",
    "R",
    "O",
    "B",
    "Y",
    "O",
    "G",
    "B",
    "O",
    "W",
    "Y",
    "B",
    "G",
    "R",
    "B",
    "O"
  ];
  function createSampleObservedFacelets(afterTurn) {
    const uPerm = afterTurn ? [6, 3, 0, 7, 4, 1, 8, 5, 2] : [0, 1, 2, 3, 4, 5, 6, 7, 8];
    const baseColors = [...SAMPLE_PREDICTED_COLORS];
    if (afterTurn) {
      const oldU = baseColors.slice(0, 9);
      uPerm.forEach((srcIdx, dstIdx) => {
        baseColors[dstIdx] = oldU[srcIdx];
      });
      const oldR = baseColors.slice(9, 12);
      const oldF = baseColors.slice(18, 21);
      const oldL = baseColors.slice(36, 39);
      const oldB = baseColors.slice(45, 48);
      baseColors.splice(36, 3, ...oldF);
      baseColors.splice(45, 3, ...oldL);
      baseColors.splice(9, 3, ...oldB);
      baseColors.splice(18, 3, ...oldR);
    }
    return baseColors.map((color, index) => {
      const faceIdx = Math.floor(index / 9);
      const face = FACE_ORDER[faceIdx];
      const localIdx = index % 9;
      const isOccludedBottom = afterTurn && face === "D";
      return {
        index,
        face,
        localIdx,
        color: isOccludedBottom ? "UNKNOWN" : color,
        confidence: isOccludedBottom ? void 0 : 0.964 + index * 7 % 4 * 8e-3,
        observationCount: isOccludedBottom ? 0 : 3,
        hasConflict: false
      };
    });
  }
  var SAMPLE_TIMELINE = [
    {
      event_id: "ev-1",
      short_label: "00:01.20 \u5B9A\u4F4D\u89C2\u6D4B",
      sim_time: 1.2,
      wall_time: "03:18:08",
      skill_name: "observe_workspace",
      stage_id: "step-1",
      duration_sec: 0.42,
      status: "VERIFIED",
      summary: "\u9876\u90E8 RGB-D \u5B9A\u4F4D\u9B54\u65B9\u4E2D\u5FC3 (SYNTHETIC SAMPLE)",
      turn_angle_deg: 0,
      contact_force_n: 0,
      gripper_width_mm: 256,
      gripper_state: "OPEN",
      completed_stage_index: 1
    },
    {
      event_id: "ev-2",
      short_label: "00:34.20 \u516D\u9762\u626B\u63CF",
      sim_time: 34.2,
      wall_time: "03:18:40",
      skill_name: "active_six_face_scan",
      stage_id: "step-2",
      duration_sec: 33,
      status: "VERIFIED",
      summary: "\u5B8C\u6210 54/54 \u8D34\u7247\u4E3B\u52A8\u626B\u63CF\u4E0E\u878D\u5408 (SYNTHETIC SAMPLE)",
      turn_angle_deg: 0,
      contact_force_n: 0,
      gripper_width_mm: 256,
      gripper_state: "OPEN",
      completed_stage_index: 3
    },
    {
      event_id: "ev-3",
      short_label: "00:58.74 \u7269\u7406\u8F6C\u9762",
      sim_time: 58.74,
      wall_time: "03:19:05",
      skill_name: "execute_physical_u_turn",
      stage_id: "step-5",
      duration_sec: 24.5,
      status: "VERIFIED",
      summary: "\u5916\u7F6E\u5939\u5177\u63A5\u89E6\u9A71\u52A8 U \u5C42\u8F6C\u52A8 +90.0\xB0 (SYNTHETIC SAMPLE)",
      turn_angle_deg: 90,
      contact_force_n: 3.46,
      gripper_width_mm: 256,
      gripper_state: "OPEN",
      completed_stage_index: 5
    },
    {
      event_id: "ev-4",
      short_label: "01:01.17 \u89C6\u89C9\u590D\u6838",
      sim_time: 61.17,
      wall_time: "03:19:08",
      skill_name: "verify_post_turn_state",
      stage_id: "step-6",
      duration_sec: 2.43,
      status: "VERIFIED",
      summary: "U \u5C42\u76F8\u5173 21 \u683C\u89C6\u89C9\u590D\u6838\u901A\u8FC7\uFF0CD \u9762\u4FDD\u6301\u672A\u77E5 (SYNTHETIC SAMPLE)",
      turn_angle_deg: 90,
      contact_force_n: 3.46,
      gripper_width_mm: 256,
      gripper_state: "OPEN",
      completed_stage_index: 6
    }
  ];
  function generateOffscreenMujocoFrameUrl(preset, turnAngleDeg, debugOverlays) {
    if (typeof document === "undefined") return "";
    const W = 1280;
    const H = 720;
    const canvas = document.createElement("canvas");
    canvas.width = W;
    canvas.height = H;
    const ctx = canvas.getContext("2d");
    if (!ctx) return "";
    const roomGrad = ctx.createLinearGradient(0, 0, 0, H);
    roomGrad.addColorStop(0, "#232B38");
    roomGrad.addColorStop(0.48, "#19212E");
    roomGrad.addColorStop(1, "#0E141F");
    ctx.fillStyle = roomGrad;
    ctx.fillRect(0, 0, W, H);
    let zoom = 1;
    let cx = W * 0.5;
    let cy = H * 0.56;
    let isTop = false;
    if (preset === "gripper_closeup") {
      zoom = 1.72;
      cy = H * 0.53;
    } else if (preset === "cube_closeup") {
      zoom = 2.28;
      cy = H * 0.47;
    } else if (preset === "top_ortho") {
      isTop = true;
      zoom = 1.15;
      cy = H * 0.51;
    }
    ctx.save();
    ctx.translate(cx, cy);
    ctx.scale(zoom, zoom);
    if (!isTop) {
      const tableGrad = ctx.createLinearGradient(0, -45, 0, 225);
      tableGrad.addColorStop(0, "#222B3B");
      tableGrad.addColorStop(1, "#141B27");
      ctx.fillStyle = tableGrad;
      ctx.beginPath();
      ctx.moveTo(-560, 210);
      ctx.lineTo(-365, -42);
      ctx.lineTo(365, -42);
      ctx.lineTo(560, 210);
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = "#3B485E";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = "#475569";
      ctx.fillRect(-465, -245, 32, 443);
      ctx.fillRect(433, -245, 32, 443);
      ctx.fillStyle = "#64748B";
      ctx.fillRect(-475, -252, 950, 44);
      ctx.fillStyle = "#0F172A";
      ctx.fillRect(-72, -258, 144, 56);
      ctx.fillStyle = "#38BDF8";
      ctx.fillRect(-58, -248, 116, 4);
    } else {
      ctx.fillStyle = "#1B2332";
      ctx.fillRect(-440, -260, 880, 520);
    }
    const rad = turnAngleDeg * Math.PI / 180;
    const isTurned90 = Math.abs(turnAngleDeg - 90) < 0.5;
    const skewShift = Math.sin(rad) * 22;
    if (isTop) {
      ctx.save();
      ctx.rotate(rad);
      ctx.fillStyle = "#0D1117";
      ctx.fillRect(-68, -68, 136, 136);
      const uCols = ["W", "R", "G", "B", "W", "Y", "O", "W", "B"];
      uCols.forEach((c, i) => {
        const r = Math.floor(i / 3);
        const col = i % 3;
        ctx.fillStyle = COLOR_MAP[c].bg;
        ctx.fillRect(-58 + col * 40, -58 + r * 40, 36, 36);
      });
      ctx.restore();
    } else {
      ctx.fillStyle = "#0D1117";
      ctx.fillRect(-68, 38, 136, 74);
      const midBotCols = ["W", "G", "O", "B", "G", "Y"];
      midBotCols.forEach((c, idx) => {
        const r = Math.floor(idx / 3);
        const col = idx % 3;
        ctx.fillStyle = COLOR_MAP[c].bg;
        ctx.fillRect(-59 + col * 40, 44 + r * 32, 36, 27);
      });
      ctx.save();
      ctx.translate(skewShift * 0.42, 0);
      ctx.fillStyle = "#0D1117";
      ctx.fillRect(-70, 0, 140, 35);
      const topRowCols = isTurned90 ? ["R", "B", "Y"] : ["G", "Y", "R"];
      topRowCols.forEach((c, col) => {
        ctx.fillStyle = COLOR_MAP[c].bg;
        ctx.fillRect(-60 + col * 41, 5, 37, 25);
      });
      ctx.restore();
    }
    if (debugOverlays.collisionGeoms) {
      ctx.strokeStyle = "#548CFF";
      ctx.setLineDash([6, 4]);
      ctx.lineWidth = 1.8;
      ctx.strokeRect(-74, -6, 148, 122);
      ctx.setLineDash([]);
    }
    if (debugOverlays.contactForces) {
      ctx.fillStyle = "#FFBF69";
      ctx.font = "bold 13px monospace";
      ctx.fillText("SAMPLE FORCE", -120, 10);
    }
    ctx.restore();
    ctx.fillStyle = "rgba(255, 191, 105, 0.9)";
    ctx.font = "bold 16px monospace";
    ctx.fillText("SYNTHETIC SAMPLE \xB7 Canvas 2D (\u975E\u771F\u5B9E MuJoCo \u5E27)", 24, 34);
    return canvas.toDataURL("image/png");
  }
  function generateSampleCameraFrames(afterTurn) {
    if (typeof document === "undefined") {
      return { rgbUrl: "", depthUrl: "", detections: [] };
    }
    const w = 480;
    const h = 300;
    const rgbCanvas = document.createElement("canvas");
    rgbCanvas.width = w;
    rgbCanvas.height = h;
    const ctx = rgbCanvas.getContext("2d");
    ctx.fillStyle = "#111827";
    ctx.fillRect(0, 0, w, h);
    const cubeX = 155;
    const cubeY = 58;
    const cubeSize = 170;
    ctx.fillStyle = "#0f131a";
    ctx.fillRect(cubeX, cubeY, cubeSize, cubeSize);
    const fColors = afterTurn ? ["R", "B", "Y", "W", "G", "O", "B", "G", "Y"] : ["G", "Y", "R", "W", "G", "O", "B", "G", "Y"];
    const detections = [];
    const pad = 10;
    const gap = 6;
    const cell = (cubeSize - pad * 2 - gap * 2) / 3;
    fColors.forEach((c, idx) => {
      const r = Math.floor(idx / 3);
      const col = idx % 3;
      const x = cubeX + pad + col * (cell + gap);
      const y = cubeY + pad + r * (cell + gap);
      ctx.fillStyle = COLOR_MAP[c].bg;
      ctx.fillRect(x, y, cell, cell);
      detections.push({
        id: `det-F-${idx}`,
        face: "F",
        localIdx: idx,
        xNorm: x / w,
        yNorm: y / h,
        wNorm: cell / w,
        hNorm: cell / h,
        color: c,
        confidence: 0.975
      });
    });
    ctx.fillStyle = "#FFBF69";
    ctx.font = "11px monospace";
    ctx.fillText("SYNTHETIC SAMPLE \xB7 RGB", 12, 20);
    const depthCanvas = document.createElement("canvas");
    depthCanvas.width = w;
    depthCanvas.height = h;
    const dctx = depthCanvas.getContext("2d");
    dctx.fillStyle = "#0f172a";
    dctx.fillRect(0, 0, w, h);
    dctx.fillStyle = "#06b6d4";
    dctx.fillRect(cubeX, cubeY, cubeSize, cubeSize);
    dctx.fillStyle = "#FFBF69";
    dctx.font = "11px monospace";
    dctx.fillText("SYNTHETIC SAMPLE \xB7 DEPTH", 12, 20);
    return {
      rgbUrl: rgbCanvas.toDataURL("image/png"),
      depthUrl: depthCanvas.toDataURL("image/png"),
      detections
    };
  }
  function createSampleSnapshot(missionType, event) {
    const ev = event || SAMPLE_TIMELINE[SAMPLE_TIMELINE.length - 1];
    const isTurnMission = missionType === "VERIFY_PHYSICAL_U_TURN";
    const afterTurn = isTurnMission && ev.turn_angle_deg >= 89.5;
    const camData = generateSampleCameraFrames(afterTurn);
    const mainFrameUrl = generateOffscreenMujocoFrameUrl(
      "overview",
      isTurnMission ? ev.turn_angle_deg : 0,
      { contactForces: true, collisionGeoms: false, tcpFrame: true }
    );
    const planStepsByMission = {
      INSPECT_CUBE: [
        {
          step_id: "smp-s1",
          index: 1,
          title: "\u5DE5\u4F5C\u7AD9\u89C2\u5BDF\u4E0E\u5B9A\u4F4D",
          skill_id: "observe_workspace",
          description: "\u9876\u90E8 RGB-D \u5B9A\u4F4D\u9B54\u65B9\u4E2D\u5FC3",
          status: "VERIFIED",
          implemented: true,
          started_sim_time: 0.4,
          ended_sim_time: 1.2,
          elapsed_sec: 0.8,
          result_summary: "\u6837\u672C\uFF1A\u5DF2\u5B9A\u4F4D\u9B54\u65B9\u4E2D\u5FC3 (SYNTHETIC SAMPLE)"
        },
        {
          step_id: "smp-s2",
          index: 2,
          title: "\u516D\u9762\u4E3B\u52A8\u626B\u63CF",
          skill_id: "active_six_face_scan",
          description: "\u4E3B\u52A8\u591A\u89C6\u89D2\u626B\u63CF\u5E76\u878D\u5408 54 \u683C",
          status: "VERIFIED",
          implemented: true,
          started_sim_time: 1.2,
          ended_sim_time: 34.2,
          elapsed_sec: 33,
          result_summary: "\u6837\u672C\uFF1A54/54 \u8D34\u7247\u89C2\u6D4B\u5B8C\u6574 (SYNTHETIC SAMPLE)"
        },
        {
          step_id: "smp-s3",
          index: 3,
          title: "54 \u683C\u5408\u6CD5\u6027\u6821\u9A8C",
          skill_id: "validate_cube_state",
          description: "\u9A8C\u8BC1 54 \u683C\u989C\u8272\u6570\u91CF\u4E0E\u7FA4\u8BBA\u53EF\u89E3\u6027",
          status: "VERIFIED",
          implemented: true,
          started_sim_time: 34.2,
          ended_sim_time: 34.25,
          elapsed_sec: 0.05,
          result_summary: "\u6837\u672C\uFF1A\u72B6\u6001\u5408\u6CD5\u53EF\u89E3\uFF0C\u672A\u8C03\u7528\u4EFB\u4F55\u7269\u7406\u8F6C\u9762"
        }
      ],
      VERIFY_PHYSICAL_U_TURN: [
        {
          step_id: "smp-u1",
          index: 1,
          title: "\u5DE5\u4F5C\u7AD9\u89C2\u5BDF\u4E0E\u5B9A\u4F4D",
          skill_id: "observe_workspace",
          description: "\u9876\u90E8 RGB-D \u5B9A\u4F4D",
          status: "VERIFIED",
          implemented: true,
          started_sim_time: 0.4,
          ended_sim_time: 1.2,
          elapsed_sec: 0.8,
          result_summary: "\u6837\u672C\uFF1A\u5DF2\u5B9A\u4F4D\u9B54\u65B9\u4E2D\u5FC3"
        },
        {
          step_id: "smp-u2",
          index: 2,
          title: "\u516D\u9762\u4E3B\u52A8\u626B\u63CF",
          skill_id: "active_six_face_scan",
          description: "54 \u683C\u626B\u63CF",
          status: "VERIFIED",
          implemented: true,
          started_sim_time: 1.2,
          ended_sim_time: 34.2,
          elapsed_sec: 33,
          result_summary: "\u6837\u672C\uFF1A54/54 \u8D34\u7247\u878D\u5408\u6210\u529F"
        },
        {
          step_id: "smp-u3",
          index: 3,
          title: "54 \u683C\u5408\u6CD5\u6027\u6821\u9A8C",
          skill_id: "validate_cube_state",
          description: "\u5408\u6CD5\u6027\u6821\u9A8C",
          status: "VERIFIED",
          implemented: true,
          started_sim_time: 34.2,
          ended_sim_time: 34.25,
          elapsed_sec: 0.05,
          result_summary: "\u6837\u672C\uFF1AVALID_SOLVABLE"
        },
        {
          step_id: "smp-u4",
          index: 4,
          title: "\u8BA1\u7B97 U \u8F6C\u52A8\u7B26\u53F7\u671F\u671B",
          skill_id: "compute_symbolic_plan",
          description: "\u7B26\u53F7\u671F\u671B\u8BA1\u7B97",
          status: "VERIFIED",
          implemented: true,
          started_sim_time: 34.25,
          ended_sim_time: 34.26,
          elapsed_sec: 0.01,
          result_summary: "\u6837\u672C\uFF1A\u751F\u6210\u5355\u6B65 U \u671F\u671B\u72B6\u6001"
        },
        {
          step_id: "smp-u5",
          index: 5,
          title: "\u63A5\u89E6\u9A71\u52A8 U \u5C42\u7269\u7406\u8F6C\u52A8",
          skill_id: "execute_physical_u_turn",
          description: "ContactUTurn \u5939\u5177\u63A5\u89E6\u62E7 U",
          status: afterTurn ? "VERIFIED" : "RUNNING",
          implemented: true,
          started_sim_time: 34.26,
          ended_sim_time: afterTurn ? 58.74 : void 0,
          elapsed_sec: afterTurn ? 24.48 : void 0,
          result_summary: afterTurn ? "\u6837\u672C\uFF1AU \u5C42\u8F6C\u89D2 90.0\xB0" : "\u6837\u672C\uFF1A\u6267\u884C\u4E2D..."
        },
        {
          step_id: "smp-u6",
          index: 6,
          title: "\u8F6C\u540E 21 \u683C\u89C6\u89C9\u590D\u6838",
          skill_id: "verify_post_turn_state",
          description: "\u72EC\u7ACB\u76F8\u673A\u590D\u6838\u53D7\u5F71\u54CD 21 \u683C",
          status: afterTurn ? "VERIFIED" : "PENDING",
          implemented: true,
          started_sim_time: afterTurn ? 58.74 : void 0,
          ended_sim_time: afterTurn ? 61.17 : void 0,
          elapsed_sec: afterTurn ? 2.43 : void 0,
          result_summary: afterTurn ? "\u6837\u672C\uFF1A21/21 \u5339\u914D\uFF0CD \u9762\u4FDD\u7559 UNKNOWN" : void 0
        }
      ],
      SOLVE_CUBE: [
        {
          step_id: "smp-k1",
          index: 1,
          title: "\u5DE5\u4F5C\u7AD9\u89C2\u5BDF\u4E0E\u5B9A\u4F4D",
          skill_id: "observe_workspace",
          description: "\u9876\u90E8 RGB-D \u5B9A\u4F4D",
          status: "VERIFIED",
          implemented: true,
          started_sim_time: 0.4,
          ended_sim_time: 1.2,
          elapsed_sec: 0.8,
          result_summary: "\u6837\u672C\uFF1A\u5DF2\u5B9A\u4F4D\u9B54\u65B9\u4E2D\u5FC3"
        },
        {
          step_id: "smp-k2",
          index: 2,
          title: "\u516D\u9762\u4E3B\u52A8\u626B\u63CF",
          skill_id: "active_six_face_scan",
          description: "54 \u683C\u626B\u63CF",
          status: "VERIFIED",
          implemented: true,
          started_sim_time: 1.2,
          ended_sim_time: 34.2,
          elapsed_sec: 33,
          result_summary: "\u6837\u672C\uFF1A54/54 \u8D34\u7247\u878D\u5408\u6210\u529F"
        },
        {
          step_id: "smp-k3",
          index: 3,
          title: "54 \u683C\u5408\u6CD5\u6027\u6821\u9A8C",
          skill_id: "validate_cube_state",
          description: "\u5408\u6CD5\u6027\u6821\u9A8C",
          status: "VERIFIED",
          implemented: true,
          started_sim_time: 34.2,
          ended_sim_time: 34.25,
          elapsed_sec: 0.05,
          result_summary: "\u6837\u672C\uFF1AVALID_SOLVABLE"
        },
        {
          step_id: "smp-k4",
          index: 4,
          title: "Kociemba \u7B26\u53F7\u6C42\u89E3",
          skill_id: "compute_symbolic_plan",
          description: "\u751F\u6210\u5B8C\u6574\u8FD8\u539F\u6B65\u5E8F",
          status: "VERIFIED",
          implemented: true,
          started_sim_time: 34.25,
          ended_sim_time: 34.27,
          elapsed_sec: 0.02,
          result_summary: "\u6837\u672C\uFF1A\u7B26\u53F7\u6C42\u89E3 21 \u6B65 [U', F', R2, ...]"
        },
        {
          step_id: "smp-k5",
          index: 5,
          title: "\u7269\u7406\u80FD\u529B\u8FB9\u754C\u6838\u67E5",
          skill_id: "check_physical_capability",
          description: "\u68C0\u67E5\u6BCF\u6B65\u662F\u5426\u5177\u6709\u771F\u5B9E\u7269\u7406 Skill",
          status: "BLOCKED",
          implemented: true,
          started_sim_time: 34.27,
          ended_sim_time: 34.27,
          elapsed_sec: 0,
          result_summary: "\u6837\u672C\uFF1A\u80FD\u529B\u963B\u585E\u4E8E\u52A8\u4F5C U' / F' / R2",
          failure_reason: "\u5F53\u524D\u4EC5\u652F\u6301\u5355\u6B21\u987A\u65F6\u9488 U \u63A5\u89E6\u7269\u7406\u8F6C\u9762\uFF0C\u4E0D\u652F\u6301\u4EFB\u610F\u516D\u9762\u8FDE\u7EED\u7269\u7406\u6C42\u89E3\u3002"
        }
      ],
      RELAY_SOLVE_CUBE: [
        {
          step_id: "smp-r1",
          index: 1,
          title: "Agent \u4E3B\u52A8\u626B\u63CF\u5EFA\u4FE1\u4E0E\u4EA4\u63A5",
          skill_id: "handover_to_human",
          description: "Gemini-3.8-Flash \u81EA\u4E3B\u6743\u8861\u7FFB\u9762\u4EE3\u4EF7\u5E76\u4EA4\u63A5\u684C\u9762",
          status: "VERIFIED",
          implemented: true,
          started_sim_time: 0.4,
          ended_sim_time: 35.1,
          elapsed_sec: 34.7,
          result_summary: "\u6837\u672C\uFF1A\u5DF2\u63D0\u4EA4\u4F4E\u4EE3\u4EF7 U \u5E76\u4E8E 2-Flip D2 \u524D\u5B89\u5168\u79FB\u4EA4\u684C\u9762"
        }
      ]
    };
    const steps = planStepsByMission[missionType];
    const missionStatus = missionType === "SOLVE_CUBE" ? "BLOCKED_CAPABILITY" : isTurnMission && !afterTurn ? "EXECUTING" : "COMPLETED";
    const spec = MISSION_OPTIONS.find((m) => m.type === missionType);
    const sampleDecisionEvents = [
      {
        event_id: "de-smp-1",
        sequence: 1,
        session_id: "SAMPLE-SEED0",
        mission_id: `msn-smp-${missionType}`,
        plan_id: `plan-smp-${missionType}`,
        event_type: "MISSION_CREATED",
        source: "SamplePacket",
        sim_time: 0.4,
        wall_time: "03:18:07",
        summary: `[SYNTHETIC SAMPLE] \u521B\u5EFA\u6837\u672C\u4EFB\u52A1 ${spec.label} (${missionType})`,
        decision_rationale_summary: "\u6B64\u4E3A\u79BB\u7EBF SYNTHETIC SAMPLE \u6570\u636E\u5305\uFF0C\u8BF7\u5207\u6362\u81F3 LIVE \u5B9E\u65F6\u4EFF\u771F\u8FD0\u884C\u771F\u5B9E MuJoCo \u540E\u7AEF\u3002",
        selected_action: missionType,
        status: "CREATED"
      },
      {
        event_id: "de-smp-2",
        sequence: 2,
        session_id: "SAMPLE-SEED0",
        mission_id: `msn-smp-${missionType}`,
        plan_id: `plan-smp-${missionType}`,
        event_type: missionType === "SOLVE_CUBE" ? "CAPABILITY_BLOCKED" : "MISSION_COMPLETED",
        source: "DeterministicMissionPlanner",
        sim_time: missionType === "SOLVE_CUBE" ? 34.27 : 61.17,
        wall_time: "03:19:08",
        summary: missionType === "SOLVE_CUBE" ? "[SYNTHETIC SAMPLE] \u52A8\u4F5C U' / R2 \u8D85\u51FA\u5355\u5C42\u7269\u7406\u80FD\u529B\uFF0C\u89E6\u53D1 CAPABILITY_BLOCKED" : `[SYNTHETIC SAMPLE] \u6837\u672C\u4EFB\u52A1 ${spec.label} \u5C55\u793A\u5B8C\u6210`,
        decision_rationale_summary: missionType === "SOLVE_CUBE" ? "Kociemba \u6C42\u89E3\u751F\u6210\u591A\u9762\u5E8F\u5217\uFF0C\u4F46 SkillRegistry \u58F0\u660E\u7269\u7406\u80FD\u529B\u4EC5\u8986\u76D6\u5355\u6B21 U \u987A\u65F6\u9488\u8F6C\u5C42\u3002" : "\u6837\u672C\u6F14\u793A\u8DEF\u5F84\u6309\u4EFB\u52A1\u76EE\u6807\u751F\u6210\u5BF9\u5E94\u8BA1\u5212\uFF08\u4E0E\u5176\u5B83\u4EFB\u52A1\u4E0D\u540C\uFF09\u3002",
        selected_action: steps[steps.length - 1].skill_id,
        skill_id: steps[steps.length - 1].skill_id,
        status: missionStatus,
        failure_reason: missionType === "SOLVE_CUBE" ? "\u7269\u7406\u80FD\u529B\u4EC5\u652F\u6301\u5355\u6B21\u987A\u65F6\u9488 U \u8F6C\u9762\uFF0C\u4E0D\u652F\u6301\u4EFB\u610F\u516D\u9762\u7269\u7406\u6267\u884C\u3002" : null
      }
    ];
    return {
      session_id: "SYNTHETIC-SAMPLE-SEED0",
      seed: 0,
      sim_time: isTurnMission ? ev.sim_time : 34.27,
      wall_time: ev.wall_time,
      frame_source: "SYNTHETIC_SAMPLE",
      active_camera: missionType === "RELAY_SOLVE_CUBE" ? "cube_closeup" : "overview",
      camera_azimuth_deg: missionType === "RELAY_SOLVE_CUBE" ? 132 : 135,
      camera_elevation_deg: -28,
      camera_distance_m: missionType === "RELAY_SOLVE_CUBE" ? 0.28 : 1.15,
      main_frame_url: mainFrameUrl || null,
      wrist_rgb_url: camData.rgbUrl || null,
      wrist_depth_url: camData.depthUrl || null,
      depth_range_m: [0.35, 2.25],
      detections: camData.detections,
      task_status: missionStatus === "COMPLETED" ? "COMPLETED" : missionStatus === "BLOCKED_CAPABILITY" ? "FAILED" : "RUNNING",
      current_stage_id: steps[steps.length - 1].step_id,
      current_skill: steps[steps.length - 1].skill_id,
      stages: steps.map((s) => ({
        id: s.step_id,
        index: s.index,
        title: s.title,
        skillName: s.skill_id,
        status: s.status,
        implemented: s.implemented,
        elapsedSec: s.elapsed_sec ?? void 0
      })),
      observed_facelets: createSampleObservedFacelets(afterTurn),
      predicted_facelets: SAMPLE_PREDICTED_COLORS,
      cube_validation_status: afterTurn ? "INCOMPLETE" : "VALID_SOLVABLE",
      telemetry: {
        contactForceN: isTurnMission ? ev.contact_force_n : 0,
        gripperWidthMm: ev.gripper_width_mm,
        gripperState: ev.gripper_state,
        jointPositionsRad: {
          robot_x: 0.35,
          robot_y: -0.32,
          robot_z: -0.02,
          wrist_yaw: 1.57,
          u_layer: afterTurn ? -1.571 : 0
        },
        cubePositionMm: [350, -320, 665],
        layerTurnAngleDeg: isTurnMission ? ev.turn_angle_deg : 0,
        targetLayer: isTurnMission ? "U" : null,
        collisionDetected: false,
        slipDetected: false,
        renderFps: 30,
        failureReason: missionType === "SOLVE_CUBE" ? "CAPABILITY_BLOCKED" : null
      },
      timeline: SAMPLE_TIMELINE,
      selected_mission_type: missionType,
      mission: {
        mission_id: `msn-smp-${missionType}`,
        session_id: "SYNTHETIC-SAMPLE-SEED0",
        mission_type: missionType,
        user_goal: spec.shortDesc,
        success_criteria: spec.capabilityNote,
        status: missionStatus,
        current_plan_id: `plan-smp-${missionType}`,
        created_at: "03:18:07",
        completed_at: "03:19:08",
        result_summary: missionType === "SOLVE_CUBE" ? "SYNTHETIC SAMPLE\uFF1A\u7B26\u53F7\u6C42\u89E3\u5B8C\u6210\uFF0C\u7269\u7406\u6267\u884C\u56E0\u80FD\u529B\u4E0D\u8DB3\u88AB\u963B\u65AD\u3002" : `SYNTHETIC SAMPLE\uFF1A${spec.label}\u6837\u672C\u9884\u89C8\u3002`,
        blocked_reason: missionType === "SOLVE_CUBE" ? "\u5F53\u524D MuJoCo \u573A\u666F\u4EC5\u5EFA\u6A21\u5355\u5C42 U \u987A\u65F6\u9488\u63A5\u89E6\u5939\u5177\uFF0C\u4E0D\u652F\u6301\u52A8\u4F5C U' / F' / R2\u3002" : null,
        blocked_move: missionType === "SOLVE_CUBE" ? "U'" : null,
        symbolic_solution: missionType === "SOLVE_CUBE" ? ["U'", "F'", "R2", "B'", "L"] : [],
        failure_reason: null
      },
      plan: {
        plan_id: `plan-smp-${missionType}`,
        mission_id: `msn-smp-${missionType}`,
        mission_type: missionType,
        planner_name: "DeterministicMissionPlanner (SYNTHETIC SAMPLE)",
        planner_mode: "DETERMINISTIC_PLANNER",
        created_at: "03:18:07",
        updated_at: "03:19:08",
        current_step_id: steps[steps.length - 1].step_id,
        steps,
        rationale_summary: "\u79BB\u7EBF\u5408\u6210\u6837\u672C\u5305\uFF0C\u4EC5\u4F5C\u9759\u6001\u754C\u9762\u5E03\u5C40\u5C55\u793A\u3002",
        replan_count: 0
      },
      decision_events: sampleDecisionEvents,
      agent_state: {
        planner_mode: "DETERMINISTIC_PLANNER",
        planner_name: "DeterministicMissionPlanner",
        llm_connected: false,
        llm_model: null,
        status_label: "\u5F53\u524D\u7531\u786E\u5B9A\u6027\u4EFB\u52A1\u89C4\u5212\u5668\u6267\u884C\uFF0CLLM Agent \u5C1A\u672A\u63A5\u5165\uFF08SYNTHETIC SAMPLE\uFF09",
        latest_observation: {
          observation_id: "obs-sample",
          frame_id: "frm-sample",
          sim_time: isTurnMission ? ev.sim_time : 34.25,
          camera_name: "synthetic_canvas2d",
          observed_count: afterTurn ? 45 : 54,
          unknown_count: afterTurn ? 9 : 0,
          conflict_count: 0,
          validation_status: afterTurn ? "INCOMPLETE" : "VALID_SOLVABLE",
          summary: "SYNTHETIC SAMPLE \u5408\u6210\u6837\u672C\u89C2\u6D4B"
        },
        selected_action: steps[steps.length - 1].skill_id,
        selection_rationale: missionType === "SOLVE_CUBE" ? "\u80FD\u529B\u6838\u67E5\u53D1\u73B0\u6C42\u89E3\u5E8F\u5217\u542B\u4E0D\u652F\u6301\u7684\u7269\u7406\u8F6C\u5C42\uFF0C\u7981\u6B62\u7ED5\u8FC7\u80FD\u529B\u8FB9\u754C\u6267\u884C\u3002" : "\u6309\u5F53\u524D Mission \u76EE\u6807\u6267\u884C\u5BF9\u5E94\u6B65\u9AA4\u5E8F\u5217\u3002",
        last_skill_call: steps[steps.length - 1].skill_id,
        last_execution_feedback: steps[steps.length - 1].result_summary || "",
        blocked_or_replan_reason: missionType === "SOLVE_CUBE" ? "\u52A8\u4F5C U' / F' / R2 \u8D85\u51FA\u5F53\u524D\u7269\u7406\u6A21\u578B\u80FD\u529B\u8303\u56F4" : null
      }
    };
  }
  function createDisconnectedLiveSnapshot(seed, missionType) {
    const faces = [];
    FACE_ORDER.forEach((face, fIdx) => {
      for (let localIdx = 0; localIdx < 9; localIdx++) {
        faces.push({
          index: fIdx * 9 + localIdx,
          face,
          localIdx,
          color: "UNKNOWN",
          observationCount: 0,
          hasConflict: false
        });
      }
    });
    return {
      session_id: "UNCONNECTED",
      seed,
      sim_time: 0,
      wall_time: "--:--:--",
      frame_source: "NONE",
      active_camera: missionType === "RELAY_SOLVE_CUBE" ? "cube_closeup" : "overview",
      camera_azimuth_deg: missionType === "RELAY_SOLVE_CUBE" ? 132 : 135,
      camera_elevation_deg: -28,
      camera_distance_m: missionType === "RELAY_SOLVE_CUBE" ? 0.28 : 1.15,
      main_frame_url: null,
      wrist_rgb_url: null,
      wrist_depth_url: null,
      depth_range_m: [0.35, 2.25],
      detections: [],
      task_status: "IDLE",
      current_stage_id: "",
      current_skill: "IDLE",
      stages: [],
      observed_facelets: faces,
      predicted_facelets: Array(54).fill("UNKNOWN"),
      cube_validation_status: "UNVERIFIED",
      telemetry: {
        contactForceN: null,
        gripperWidthMm: null,
        gripperState: "UNKNOWN",
        jointPositionsRad: null,
        cubePositionMm: null,
        layerTurnAngleDeg: null,
        targetLayer: null,
        collisionDetected: null,
        slipDetected: null,
        renderFps: null,
        failureReason: null
      },
      timeline: [],
      selected_mission_type: missionType,
      mission: null,
      plan: null,
      skill_executions: [],
      decision_events: [],
      capabilities: null,
      agent_state: {
        planner_mode: "UNCONNECTED",
        planner_name: "\u672A\u8FDE\u63A5",
        llm_connected: false,
        llm_model: null,
        status_label: "\u672A\u8FDE\u63A5\u540E\u7AEF \xB7 Agent \u5C1A\u672A\u63A5\u5165"
      },
      physical_verification: null,
      last_observation_ref: null,
      running: false,
      relay_phase: "IDLE",
      relay_state: null
    };
  }
  function formatSimTime(sec) {
    const mins = Math.floor(sec / 60);
    const rem = sec - mins * 60;
    return `${String(mins).padStart(2, "0")}:${rem.toFixed(2).padStart(5, "0")}`;
  }
  var StageStatusBadge = ({ status, implemented }) => {
    if (!implemented || status === "UNAVAILABLE") {
      return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-800/80 text-slate-400 border border-slate-700/80", children: "\u4E0D\u53EF\u7528" });
    }
    switch (status) {
      case "VERIFIED":
        return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#30D6A0]/15 text-[#30D6A0] border border-[#30D6A0]/40", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CircleCheck, { className: "w-2.5 h-2.5" }),
          " \u5DF2\u5B8C\u6210"
        ] });
      case "RUNNING":
        return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#548CFF]/20 text-[#548CFF] border border-[#548CFF]/50", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RefreshCw, { className: "w-2.5 h-2.5 animate-spin" }),
          " \u6267\u884C\u4E2D"
        ] });
      case "BLOCKED":
        return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#FFBF69]/15 text-[#FFBF69] border border-[#FFBF69]/40", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ShieldAlert, { className: "w-2.5 h-2.5" }),
          " \u80FD\u529B\u963B\u585E"
        ] });
      case "FAILED":
        return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#FF667B]/15 text-[#FF667B] border border-[#FF667B]/40", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CircleX, { className: "w-2.5 h-2.5" }),
          " \u5931\u8D25"
        ] });
      default:
        return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#182338] text-slate-400 border border-slate-700/60", children: "\u7B49\u5F85\u4E2D" });
    }
  };
  var MissionStatusBadge = ({ status }) => {
    if (!status) {
      return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-mono bg-[#182338] text-slate-400 border border-slate-700", children: "IDLE" });
    }
    const styles = {
      CREATED: "bg-[#182338] text-slate-300 border-slate-700",
      OBSERVING: "bg-[#3DE8E5]/15 text-[#3DE8E5] border-[#3DE8E5]/40",
      PLANNING: "bg-[#548CFF]/20 text-[#548CFF] border-[#548CFF]/40",
      EXECUTING: "bg-[#548CFF]/20 text-[#548CFF] border-[#548CFF]/50",
      VERIFYING: "bg-[#3DE8E5]/15 text-[#3DE8E5] border-[#3DE8E5]/40",
      WAITING_FOR_HUMAN_TURN: "bg-[#FFBF69]/20 text-[#FFBF69] border-[#FFBF69]/50",
      BLOCKED_CAPABILITY: "bg-[#FFBF69]/20 text-[#FFBF69] border-[#FFBF69]/50",
      COMPLETED: "bg-[#30D6A0]/15 text-[#30D6A0] border-[#30D6A0]/40",
      FAILED: "bg-[#FF667B]/15 text-[#FF667B] border-[#FF667B]/40",
      CANCELLED: "bg-slate-800 text-slate-300 border-slate-600"
    };
    return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: `px-1.5 py-0.5 rounded text-[10px] font-mono border ${styles[status]}`, children: status });
  };
  var SimulationViewport = ({
    mode,
    wsConnected,
    wsUrl,
    snapshot,
    debugOverlays,
    onCameraPresetChange,
    onCameraOrbitCommand,
    onCameraZoomCommand,
    previewScreenshotUrl,
    onUploadPreviewScreenshot,
    replayVideoRef,
    replayVideoUrl,
    onReplayTimeUpdate,
    onLoadReplayFiles,
    onUrgentInterrupt
  }) => {
    const dragStateRef = (0, import_react3.useRef)({
      active: false,
      lastX: 0,
      lastY: 0
    });
    const lastWheelRef = (0, import_react3.useRef)(0);
    const handlePointerDown = (e) => {
      if (mode !== "LIVE" || !wsConnected) return;
      const target = e.target;
      if (target.closest('button, input, select, textarea, a, [role="button"]')) return;
      dragStateRef.current = { active: true, lastX: e.clientX, lastY: e.clientY };
      e.currentTarget.setPointerCapture(e.pointerId);
    };
    const handlePointerMove = (e) => {
      if (!dragStateRef.current.active || mode !== "LIVE" || !wsConnected) return;
      const dx = e.clientX - dragStateRef.current.lastX;
      const dy = e.clientY - dragStateRef.current.lastY;
      dragStateRef.current.lastX = e.clientX;
      dragStateRef.current.lastY = e.clientY;
      if (Math.abs(dx) > 1 || Math.abs(dy) > 1) {
        onCameraOrbitCommand(-dx * 0.35, dy * 0.25);
      }
    };
    const handlePointerUp = (e) => {
      if (dragStateRef.current.active) {
        dragStateRef.current.active = false;
        e.currentTarget.releasePointerCapture(e.pointerId);
      }
    };
    const handleWheel = (e) => {
      if (mode !== "LIVE" || !wsConnected) return;
      e.preventDefault();
      const now = performance.now();
      if (now - lastWheelRef.current < 45) return;
      lastWheelRef.current = now;
      onCameraZoomCommand(e.deltaY > 0 ? 0.04 : -0.04);
    };
    const azRad = snapshot.camera_azimuth_deg * Math.PI / 180;
    const elRad = snapshot.camera_elevation_deg * Math.PI / 180;
    const axisX = { x: Math.cos(azRad) * 18, y: Math.sin(azRad) * Math.sin(elRad) * 18 };
    const axisY = { x: -Math.sin(azRad) * 18, y: Math.cos(azRad) * Math.sin(elRad) * 18 };
    const axisZ = { x: 0, y: -Math.cos(elRad) * 18 };
    const activeStep = snapshot.plan?.steps.find((s) => s.step_id === snapshot.plan?.current_step_id);
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
      "div",
      {
        className: "relative w-full h-full bg-[#080D16] border border-slate-800/90 rounded-lg overflow-hidden select-none flex flex-col",
        onPointerDown: handlePointerDown,
        onPointerMove: handlePointerMove,
        onPointerUp: handlePointerUp,
        onWheel: handleWheel,
        children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "z-20 flex items-center justify-between gap-2 px-3 py-1.5 bg-[#101827]/95 border-b border-slate-800/90 shrink-0", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-2 min-w-0", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Monitor, { className: "w-3.5 h-3.5 text-[#3DE8E5] shrink-0" }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[11px] font-semibold tracking-wider text-slate-200 uppercase truncate", children: "\u5B9E\u65F6\u4EFF\u771F\u89C6\u53E3 \xB7 MuJoCo Renderer" }),
              mode === "SAMPLE" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-[#FFBF69]/15 text-[#FFBF69] border border-[#FFBF69]/40 shrink-0", children: "SYNTHETIC SAMPLE \xB7 Canvas 2D \u6837\u672C (Seed=0)" }),
              mode === "LIVE" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                "span",
                {
                  className: `inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono shrink-0 ${wsConnected ? "bg-[#30D6A0]/15 text-[#30D6A0] border border-[#30D6A0]/40" : "bg-[#FF667B]/15 text-[#FF667B] border border-[#FF667B]/40"}`,
                  children: wsConnected ? "LIVE \xB7 REAL MUJOCO RENDERER" : "LIVE \xB7 \u672A\u8FDE\u63A5\u540E\u7AEF"
                }
              ),
              mode === "REPLAY" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-[#548CFF]/15 text-[#548CFF] border border-[#548CFF]/40 shrink-0", children: "PREVIEW / REPLAY \xB7 \u5916\u90E8\u5F55\u5236\u4E0E\u622A\u56FE\u6A21\u5F0F" })
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1 bg-[#080D16] p-0.5 rounded border border-slate-800 shrink-0", children: [
              CAMERA_PRESETS.map((cam) => {
                const active = snapshot.active_camera === cam.id;
                return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                  "button",
                  {
                    type: "button",
                    title: cam.desc,
                    onClick: () => onCameraPresetChange(cam.id),
                    className: `px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${active ? "bg-[#548CFF] text-white" : "text-slate-400 hover:text-slate-200 hover:bg-[#182338]"}`,
                    children: cam.label
                  },
                  cam.id
                );
              }),
              mode === "LIVE" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                  "button",
                  {
                    type: "button",
                    title: "\u62C9\u8FD1\u955C\u5934\u653E\u5927\u9B54\u65B9",
                    onClick: () => onCameraZoomCommand(-0.05),
                    className: "px-1.5 py-0.5 rounded text-[11px] font-mono text-[#3DE8E5] hover:bg-[#182338]",
                    children: "+\u653E\u5927"
                  }
                ),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                  "button",
                  {
                    type: "button",
                    title: "\u62C9\u8FDC\u955C\u5934",
                    onClick: () => onCameraZoomCommand(0.05),
                    className: "px-1.5 py-0.5 rounded text-[11px] font-mono text-slate-300 hover:bg-[#182338]",
                    children: "-\u7F29\u5C0F"
                  }
                )
              ] })
            ] })
          ] }),
          (snapshot.selected_mission_type === "RELAY_SOLVE_CUBE" || snapshot.relay_state?.enabled) && (() => {
            const relay = snapshot.relay_state;
            const tone = relay?.banner?.tone || "slate";
            const toneClass = tone === "amber" ? "bg-[#FFBF69]/15 border-[#FFBF69]/50 text-[#FFBF69]" : tone === "violet" ? "bg-[#8B5CF6]/15 border-[#8B5CF6]/50 text-[#A78BFA]" : tone === "emerald" ? "bg-[#30D6A0]/15 border-[#30D6A0]/50 text-[#30D6A0]" : tone === "red" ? "bg-[#FF667B]/15 border-[#FF667B]/50 text-[#FF667B]" : tone === "blue" ? "bg-[#548CFF]/15 border-[#548CFF]/50 text-[#3DE8E5]" : "bg-[#182338] border-slate-700 text-slate-300";
            const prog = relay?.progress;
            const pct = prog ? Math.max(0, Math.min(100, prog.completion_pct)) : 0;
            const stats = relay?.cognitive_stats;
            const turnInfo = relay?.turn_indicator;
            const owner = turnInfo?.owner || (relay?.phase === "WAITING_FOR_HUMAN_TURN" ? "HUMAN" : relay?.phase === "AWAITING_HUMAN_CLARIFICATION" ? "CLARIFY" : relay?.phase === "RELAY_COMPLETED_VERIFIED" ? "DONE" : relay?.phase === "ROBOT_ACTING" || relay?.phase === "AGENT_REASONING" || relay?.phase === "ROBOT_PERCEIVING" || relay?.phase === "VERIFYING_SOLVED" ? "ROBOT" : "IDLE");
            const ownerPillCls = owner === "HUMAN" ? "bg-[#FFBF69]/20 text-[#FFBF69] border-[#FFBF69] animate-pulse" : owner === "CLARIFY" ? "bg-[#8B5CF6]/20 text-[#A78BFA] border-[#8B5CF6]/50 animate-pulse" : owner === "ROBOT" ? "bg-[#3DE8E5]/15 text-[#3DE8E5] border-[#3DE8E5]/50 animate-pulse" : owner === "DONE" ? "bg-[#30D6A0]/20 text-[#30D6A0] border-[#30D6A0]/50" : "bg-[#182338] text-slate-300 border-slate-700";
            const ownerText = turnInfo?.owner_label_zh || (owner === "HUMAN" ? "\u{1F9D1} \u5F53\u524D\u56DE\u5408\uFF1A\u4EBA\u7C7B\u64CD\u4F5C\u4E2D" : owner === "CLARIFY" ? "\u{1F7E3} \u5F53\u524D\u56DE\u5408\uFF1A\u5F85\u4F60\u786E\u8BA4" : owner === "ROBOT" ? "\u{1F916} \u5F53\u524D\u56DE\u5408\uFF1A\u673A\u5668\u4EBA\u6267\u884C\u4E2D" : owner === "DONE" ? "\u{1F389} 100% \u590D\u539F\u5DF2\u5B8C\u6210" : "\u23F8\uFE0F \u5F85\u542F\u52A8");
            const stageLabels = turnInfo?.stage_labels || ["\u5F00\u5C40\u626B\u9762", "\u673A\u5668\u4EBA\u64CD\u4F5C", "\u4EA4\u63A5/\u6F84\u6E05", "\u4EBA\u7C7B\u56DE\u5408", "\u5FEB\u7784/\u4FEE\u590D", "\u590D\u539F\u6838\u9A8C"];
            const stageIdx = typeof turnInfo?.stage_index === "number" ? turnInfo.stage_index : owner === "HUMAN" ? 3 : owner === "CLARIFY" ? 2 : owner === "DONE" ? 5 : relay?.phase === "ROBOT_PERCEIVING" ? 0 : owner === "ROBOT" ? 1 : 0;
            return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "z-20 px-3 py-1.5 bg-[#0C1422] border-b border-slate-800/90 space-y-1.5 shrink-0", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: `px-2.5 py-1.5 rounded border flex items-center justify-between gap-2 ${toneClass}`, children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "min-w-0 flex items-center gap-2", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: `px-2 py-0.5 rounded border text-[10.5px] font-bold shrink-0 ${ownerPillCls}`, children: ownerText }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "min-w-0", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[11px] font-semibold truncate", children: relay?.banner?.title_zh || "\u{1F9D1}/\u{1F916} Agent \u4EBA\u673A\u63A5\u529B\u5F85\u547D" }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[9.5px] opacity-85 truncate", children: turnInfo?.next_action_hint_zh || relay?.banner?.subtitle_zh || "\u9009\u62E9\u6253\u4E71\u6B65\u6570\u5E76\u542F\u52A8\uFF0C\u5B9E\u65F6\u89C2\u770B\u9B54\u65B9 26 \u5757\u534F\u540C\u590D\u539F\u3002" })
                  ] })
                ] }),
                snapshot.running && (relay?.phase === "ROBOT_ACTING" || relay?.phase === "AGENT_REASONING") && onUrgentInterrupt && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                  "button",
                  {
                    type: "button",
                    onClick: onUrgentInterrupt,
                    className: "px-2 py-1 rounded text-[10px] font-semibold bg-[#FF667B]/20 hover:bg-[#FF667B]/30 text-[#FF667B] border border-[#FF667B]/50 shrink-0 transition-colors",
                    children: "\u26A1 \u7D27\u6025\u5239\u8F66/\u4E2D\u65AD"
                  }
                )
              ] }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "grid grid-cols-6 gap-1 text-[9.5px] font-mono", children: stageLabels.map((stLabel, idx) => {
                const isDoneStage = owner === "DONE" ? true : idx < stageIdx;
                const isCurStage = owner !== "DONE" && idx === stageIdx;
                const stageCls = isCurStage ? "bg-[#3DE8E5]/15 text-[#3DE8E5] border-[#3DE8E5]/60 font-semibold" : isDoneStage ? "bg-[#30D6A0]/10 text-[#30D6A0] border-[#30D6A0]/30" : "bg-[#080D16] text-slate-500 border-slate-800";
                return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: `px-1.5 py-0.5 rounded border text-center truncate ${stageCls}`, children: [
                  isDoneStage ? "\u2713 " : isCurStage ? "\u25CF " : `${idx + 1}. `,
                  stLabel
                ] }, stLabel);
              }) }),
              relay && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-1", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-2 text-[10px] font-mono text-slate-300", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-2 min-w-0 truncate", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                      "\u5269\u4F59: ",
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("strong", { className: "text-[#3DE8E5]", children: prog?.initial_optimal_steps ?? "--" }),
                      " \u2192",
                      " ",
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("strong", { className: "text-[#30D6A0]", children: prog?.remaining_optimal_steps ?? "--" }),
                      " \u6B65 (",
                      pct.toFixed(0),
                      "%)"
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-500", children: "\xB7" }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                      "\u7B2C ",
                      relay.round_number || 1,
                      " \u8F6E"
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-500", children: "\xB7" }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                      "\u{1F916}",
                      prog?.robot_moves_count ?? 0,
                      "\u6B65 / \u{1F9D1}",
                      prog?.human_turns_count ?? 0,
                      "\u8F6E"
                    ] })
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1.5 shrink-0 text-[9.5px]", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "px-1.5 py-0.5 rounded bg-[#182338] border border-slate-700 text-[#3DE8E5]", children: [
                      "\u5FEB\u7784\u514D\u7FFB:",
                      stats?.rapid_glance_deduction_successes ?? 0
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "px-1.5 py-0.5 rounded bg-[#182338] border border-slate-700 text-[#FFBF69]", children: [
                      "\u7701\u7FFB\u9762:",
                      stats?.saved_high_cost_flips ?? 0
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "px-1.5 py-0.5 rounded bg-[#182338] border border-slate-700 text-slate-300", children: [
                      "\u62A2\u5360:",
                      stats?.fast_loop_contract_interceptions ?? 0
                    ] })
                  ] })
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "w-full h-1.5 bg-[#182338] rounded-full overflow-hidden border border-slate-800", children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                  "div",
                  {
                    className: "h-full bg-[#30D6A0] transition-all",
                    style: { width: `${pct}%` }
                  }
                ) }),
                prog?.round_tags && prog.round_tags.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "flex items-center gap-1 overflow-x-auto text-[9.5px] font-mono", children: prog.round_tags.map((tag, i) => {
                  const isLatest = i === prog.round_tags.length - 1;
                  const tagCls = isLatest ? "bg-[#3DE8E5]/15 border-[#3DE8E5]/50 text-[#3DE8E5] font-semibold" : "bg-[#182338] border-slate-700 text-slate-400";
                  return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                    "span",
                    {
                      className: `px-1.5 py-0.5 rounded border shrink-0 ${tagCls}`,
                      children: tag
                    },
                    `${tag}-${i}`
                  );
                }) })
              ] })
            ] });
          })(),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "relative flex-1 flex items-center justify-center bg-[#080D16] overflow-hidden", children: [
            mode === "SAMPLE" && snapshot.main_frame_url && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "img",
              {
                src: snapshot.main_frame_url,
                alt: "SYNTHETIC SAMPLE Frame",
                className: "w-full h-full object-contain",
                draggable: false
              }
            ),
            mode === "LIVE" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_jsx_runtime.Fragment, { children: wsConnected && snapshot.main_frame_url ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "img",
              {
                src: snapshot.main_frame_url,
                alt: "Real MuJoCo Offscreen Render Frame",
                className: "w-full h-full object-contain",
                draggable: false
              }
            ) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "z-10 max-w-md mx-auto p-5 rounded-lg bg-[#101827]/95 border border-slate-800 text-center space-y-2.5", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "w-10 h-10 mx-auto rounded-full bg-[#182338] border border-slate-700 flex items-center justify-center text-[#FFBF69]", children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(WifiOff, { className: "w-5 h-5" }) }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-xs font-semibold text-slate-100", children: wsConnected ? "\u5DF2\u8FDE\u63A5 SimulationSession\uFF0C\u7B49\u5F85\u771F\u5B9E MuJoCo \u9996\u5E27..." : "\u672A\u8FDE\u63A5\u5230 Python MuJoCo \u4EFF\u771F\u540E\u7AEF" }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { className: "text-[11px] text-slate-400 leading-relaxed", children: [
                "LIVE \u6A21\u5F0F\u4E25\u683C\u63A5\u6536\u540E\u7AEF ",
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("code", { className: "text-[#3DE8E5] font-mono", children: "mujoco.Renderer" }),
                " \u5E27\u6D41\uFF0C\u7EDD\u4E0D\u4F7F\u7528 Canvas 2D \u5408\u6210\u56FE\u3002"
              ] }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2 rounded bg-[#080D16] border border-slate-800 font-mono text-[10px] text-slate-300 text-left", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
                  "\u7AEF\u70B9: ",
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[#3DE8E5]", children: wsUrl })
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-slate-500 mt-0.5", children: "\u542F\u52A8: python -m cube_relay.server --seed 0 --port 8765" })
              ] })
            ] }) }),
            mode === "REPLAY" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_jsx_runtime.Fragment, { children: replayVideoUrl ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "video",
              {
                ref: replayVideoRef,
                src: replayVideoUrl,
                className: "w-full h-full object-contain bg-black",
                controls: true,
                onTimeUpdate: (e) => onReplayTimeUpdate(e.currentTarget.currentTime)
              }
            ) : previewScreenshotUrl ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "img",
              {
                src: previewScreenshotUrl,
                alt: "Historical MuJoCo Run Screenshot",
                className: "w-full h-full object-contain"
              }
            ) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "z-10 max-w-md mx-auto p-5 rounded-lg bg-[#101827]/95 border border-slate-800 text-center space-y-2.5", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "w-10 h-10 mx-auto rounded-full bg-[#182338] border border-slate-700 flex items-center justify-center text-[#548CFF]", children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Film, { className: "w-5 h-5" }) }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-xs font-semibold text-slate-100", children: "\u79BB\u7EBF\u754C\u9762\u9884\u89C8 / \u5BFC\u5165\u672C\u5730\u5386\u53F2\u8FD0\u884C\u6587\u4EF6" }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { className: "text-[11px] text-slate-400 leading-relaxed", children: [
                "\u652F\u6301\u5BFC\u5165\u771F\u5B9E ",
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("code", { className: "text-slate-300 font-mono", children: "episode.mp4" }),
                " +",
                " ",
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("code", { className: "text-slate-300 font-mono", children: "episode.timing.json" }),
                " \u6216\u5386\u53F2\u8FD0\u884C\u622A\u56FE\u3002"
              ] }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-center gap-2 pt-1", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-[#548CFF] hover:bg-[#4379eb] text-white text-xs font-medium cursor-pointer transition-colors", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(FolderOpen, { className: "w-3.5 h-3.5" }),
                  "\u5BFC\u5165\u5F55\u50CF\u4E0E\u65F6\u95F4\u8F74",
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                    "input",
                    {
                      type: "file",
                      accept: "video/mp4,application/json",
                      multiple: true,
                      className: "hidden",
                      onChange: (e) => {
                        const files = Array.from(e.target.files || []);
                        const vFile = files.find((f) => f.name.endsWith(".mp4")) || null;
                        const tFile = files.find((f) => f.name.endsWith(".json")) || null;
                        onLoadReplayFiles(vFile, tFile);
                      }
                    }
                  )
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-[#182338] hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-medium cursor-pointer transition-colors", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Upload, { className: "w-3.5 h-3.5 text-[#3DE8E5]" }),
                  "\u8F7D\u5165\u5386\u53F2\u622A\u56FE",
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                    "input",
                    {
                      type: "file",
                      accept: "image/png,image/jpeg,image/webp",
                      className: "hidden",
                      onChange: (e) => {
                        const f = e.target.files?.[0];
                        if (f) onUploadPreviewScreenshot(URL.createObjectURL(f));
                      }
                    }
                  )
                ] })
              ] })
            ] }) }),
            debugOverlays.hudVisible && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "pointer-events-none absolute top-2.5 left-2.5 z-10 flex flex-col gap-1 bg-[#080D16]/85 backdrop-blur-xs border border-slate-800/90 rounded px-2.5 py-1.5 text-[11px]", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-2", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-400", children: "\u5F53\u524D Mission:" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "font-mono font-semibold text-slate-100", children: snapshot.mission?.mission_type || snapshot.selected_mission_type || "INSPECT_CUBE" })
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-2", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-400", children: "\u5F53\u524D\u6B65\u9AA4:" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "font-medium text-slate-100", children: activeStep?.title || snapshot.stages.find((s) => s.id === snapshot.current_stage_id)?.title || "\u5C31\u7EEA" })
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-2", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-400", children: "\u6267\u884C Skill:" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "font-mono text-[#3DE8E5]", children: snapshot.current_skill })
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-2.5 font-mono text-[10px] text-slate-300 pt-0.5 border-t border-slate-800", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                    "SIM: ",
                    formatSimTime(snapshot.sim_time),
                    "s"
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                    "SEED: ",
                    snapshot.seed
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                    "SRC: ",
                    snapshot.frame_source || "NONE"
                  ] })
                ] })
              ] }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "pointer-events-none absolute bottom-2.5 left-2.5 z-10 flex items-center gap-2 bg-[#080D16]/85 border border-slate-800/90 rounded px-2 py-1", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("svg", { width: "42", height: "42", viewBox: "-22 -22 44 44", className: "overflow-visible", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("line", { x1: "0", y1: "0", x2: axisX.x, y2: axisX.y, stroke: "#FF667B", strokeWidth: "1.8" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("text", { x: axisX.x * 1.25, y: axisX.y * 1.25, fill: "#FF667B", fontSize: "8", fontFamily: "monospace", textAnchor: "middle", children: "X" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("line", { x1: "0", y1: "0", x2: axisY.x, y2: axisY.y, stroke: "#30D6A0", strokeWidth: "1.8" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("text", { x: axisY.x * 1.25, y: axisY.y * 1.25, fill: "#30D6A0", fontSize: "8", fontFamily: "monospace", textAnchor: "middle", children: "Y" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("line", { x1: "0", y1: "0", x2: axisZ.x, y2: axisZ.y, stroke: "#548CFF", strokeWidth: "1.8" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("text", { x: axisZ.x * 1.25, y: axisZ.y * 1.25, fill: "#548CFF", fontSize: "8", fontFamily: "monospace", textAnchor: "middle", children: "Z" })
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[10px] font-mono text-slate-400 leading-tight", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
                    "AZ: ",
                    snapshot.camera_azimuth_deg.toFixed(0),
                    "\xB0"
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
                    "EL: ",
                    snapshot.camera_elevation_deg.toFixed(0),
                    "\xB0"
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
                    "D: ",
                    snapshot.camera_distance_m.toFixed(2),
                    "m"
                  ] })
                ] })
              ] })
            ] })
          ] })
        ]
      }
    );
  };
  var RELAY_FACE_GROUPS = [
    { face: "U", moves: ["U", "U'", "U2"] },
    { face: "D", moves: ["D", "D'", "D2"] },
    { face: "F", moves: ["F", "F'", "F2"] },
    { face: "B", moves: ["B", "B'", "B2"] },
    { face: "L", moves: ["L", "L'", "L2"] },
    { face: "R", moves: ["R", "R'", "R2"] }
  ];
  var QUICK_HRI_CHIPS = [
    { label: "\u4EA4\u7ED9\u4F60\u590D\u539F", text: "\u6211\u4E0D\u73A9\u4E86\uFF0C\u5269\u4E0B\u7684\u5168\u90E8\u4EA4\u7ED9\u4F60\u590D\u539F\uFF01" },
    { label: "\u62D2\u62E7\u5E95\u9762D", text: "\u5E95\u9762D\u6211\u4E0D\u65B9\u4FBF\u62E7\uFF0C\u5E95\u9762\u7531\u4F60\u7FFB\u9762\u62E7\u6389\uFF0C\u7ED9\u6211\u7559\u9876\u9762\u6216\u4FA7\u9762" },
    { label: "\u624B\u6ED1\u64A4\u56DE", text: "\u521A\u624D\u624B\u6ED1\u62E7\u9519\u4E86\uFF0C\u5E2E\u6211\u64A4\u56DE\u4E0A\u4E00\u6B65" },
    { label: "\u987A\u8DEF\u7EBF\u89E3", text: "\u6211\u662F\u6545\u610F\u6362\u8DEF\u7EBF\u7684\uFF0C\u8BF7\u4FDD\u7559\u6211\u7684\u52A8\u4F5C\u987A\u7740\u7EE7\u7EED\u5F80\u4E0B\u89E3" },
    { label: "\u7D27\u6025\u653E\u56DE", text: "\u505C\u4E00\u4E0B\uFF01\u5148\u522B\u89E3\u4E86\uFF0C\u628A\u9B54\u65B9\u5B89\u5168\u653E\u56DE\u684C\u9762\u4EA4\u7ED9\u6211" }
  ];
  var RightOrchestrationPanel = ({
    mode,
    snapshot,
    selectedMission,
    selectedScrambleSteps,
    onSelectMission,
    onSelectScrambleSteps,
    onRelayCommand
  }) => {
    const [rightTab, setRightTab] = (0, import_react3.useState)("AGENT");
    const [showLegacyMissions, setShowLegacyMissions] = (0, import_react3.useState)(false);
    const [agentDrawerOpen, setAgentDrawerOpen] = (0, import_react3.useState)(false);
    const [skillDrawerOpen, setSkillDrawerOpen] = (0, import_react3.useState)(false);
    const [expandedSkills, setExpandedSkills] = (0, import_react3.useState)(/* @__PURE__ */ new Set());
    const [expandedTraceEvents, setExpandedTraceEvents] = (0, import_react3.useState)(/* @__PURE__ */ new Set());
    const [selectedDecisionObservationId, setSelectedDecisionObservationId] = (0, import_react3.useState)(null);
    const [chatDraft, setChatDraft] = (0, import_react3.useState)("");
    const [perturbDxCm, setPerturbDxCm] = (0, import_react3.useState)(0);
    const [perturbDyCm, setPerturbDyCm] = (0, import_react3.useState)(0);
    const [perturbYawDeg, setPerturbYawDeg] = (0, import_react3.useState)(0);
    (0, import_react3.useEffect)(() => {
      if (snapshot.relay_state?.perturbation) {
        setPerturbDxCm(Math.round((snapshot.relay_state.perturbation.dx_m || 0) * 100));
        setPerturbDyCm(Math.round((snapshot.relay_state.perturbation.dy_m || 0) * 100));
        setPerturbYawDeg(Math.round(snapshot.relay_state.perturbation.dyaw_deg || 0));
      }
    }, [snapshot.relay_state?.phase, snapshot.relay_state?.perturbation?.dx_m, snapshot.relay_state?.perturbation?.dy_m, snapshot.relay_state?.perturbation?.dyaw_deg]);
    const mission = snapshot.mission;
    const plan = snapshot.plan;
    const agent = snapshot.agent_state;
    const decisionEvents = snapshot.decision_events || [];
    const executions = snapshot.skill_executions || [];
    const traceEvents = snapshot.trace_events || [];
    const policyTraceEvents = traceEvents.filter((event) => event.event_type === "decision");
    const vlmCompositeTrace = traceEvents.find(
      (event) => event.event_type === "composite_skill" && event.skill_id === "vlm_controlled_inspection"
    );
    const vlmCompositeChildren = vlmCompositeTrace ? traceEvents.filter((event) => event.parent_event_id === vlmCompositeTrace.event_id) : [];
    const missionSpec = MISSION_OPTIONS.find((m) => m.type === selectedMission);
    const selectedDecisionObservation = (snapshot.observations || []).find(
      (observation) => observation.observation_id === selectedDecisionObservationId
    );
    const completedSteps = plan ? plan.steps.filter((s) => s.status === "VERIFIED").length : 0;
    const totalSteps = plan ? plan.steps.length : 0;
    const isVlmPlanner = agent?.planner_mode === "LLM_AGENT";
    const plannerBannerStyle = agent?.llm_connected ? "bg-[#30D6A0]/10 border-[#30D6A0]/40 text-[#30D6A0]" : isVlmPlanner ? "bg-[#FFBF69]/10 border-[#FFBF69]/40 text-[#FFBF69]" : agent?.planner_mode === "DETERMINISTIC_PLANNER" ? "bg-[#548CFF]/15 border-[#548CFF]/40 text-slate-200" : "bg-[#182338] border-slate-700 text-slate-300";
    const safetyGateStyle = agent?.safety_gate_status && agent.safety_gate_status.startsWith("PASSED") ? "text-[#30D6A0]" : agent?.safety_gate_status && agent.safety_gate_status.includes("BLOCKED") ? "text-[#FFBF69]" : agent?.safety_gate_status ? "text-[#FF667B]" : "text-slate-400";
    const isRelayMission = selectedMission === "RELAY_SOLVE_CUBE";
    const showAgentPanel = isRelayMission ? agentDrawerOpen : rightTab === "AGENT";
    const showSkillPanel = isRelayMission ? skillDrawerOpen : rightTab === "SKILL";
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "min-w-0 min-h-0 h-full bg-[#101827] border border-slate-800/90 rounded-lg p-2.5 flex flex-col gap-2", children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-1.5 border-b border-slate-800/90 pb-2 shrink-0", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-1.5", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1.5 min-w-0", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(GitBranch, { className: "w-3.5 h-3.5 text-[#3DE8E5] shrink-0" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[11px] font-semibold tracking-wider text-slate-200 uppercase truncate", children: isRelayMission ? "\u{1F9D1}/\u{1F916} \u4EBA\u673A\u63A5\u529B\u4E3B\u63A7\u53F0" : `\u5B9E\u9A8C\u6A21\u5F0F \xB7 ${missionSpec.label}` })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1.5 shrink-0", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "button",
              {
                type: "button",
                onClick: () => setShowLegacyMissions((v) => !v),
                title: "\u5C55\u5F00/\u6536\u8D77\u5386\u53F2\u5355\u9636\u6BB5\u5B9E\u9A8C\uFF08\u516D\u9762\u626B\u63CF / U\u5C42\u7269\u7406\u8F6C\u52A8 / \u9B54\u65B9\u5B8C\u6574\u6C42\u89E3\uFF09",
                className: "px-1.5 py-0.5 rounded text-[9.5px] bg-[#080D16] hover:bg-[#182338] text-slate-400 hover:text-slate-200 border border-slate-800 transition-colors",
                children: showLegacyMissions ? "\u6536\u8D77\u5386\u53F2\u5B9E\u9A8C \u25B4" : "\u5386\u53F2\u5B9E\u9A8C \u25BE"
              }
            ),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(MissionStatusBadge, { status: mission?.status })
          ] })
        ] }),
        (showLegacyMissions || !isRelayMission) && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "grid grid-cols-2 gap-1 bg-[#080D16] p-0.5 rounded border border-slate-800", children: MISSION_OPTIONS.map((opt) => {
          const active = selectedMission === opt.type;
          return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            "button",
            {
              type: "button",
              title: opt.shortDesc,
              onClick: () => onSelectMission(opt.type),
              className: `px-1.5 py-1 rounded text-[10.5px] font-medium truncate transition-colors ${active ? "bg-[#548CFF] text-white" : "text-slate-400 hover:text-slate-200 hover:bg-[#182338]"}`,
              children: opt.label
            },
            opt.type
          );
        }) }),
        isRelayMission && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-1 bg-[#080D16] border border-slate-800 rounded px-2 py-1 text-[10px]", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-400 shrink-0", children: "\u6253\u4E71\u6B65\u6570:" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "flex items-center gap-1", children: [4, 5, 6, 8, "random"].map((opt) => {
            const active = selectedScrambleSteps === opt;
            return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "button",
              {
                type: "button",
                onClick: () => onSelectScrambleSteps(opt),
                className: `px-1.5 py-0.5 rounded font-mono transition-colors ${active ? "bg-[#3DE8E5]/20 text-[#3DE8E5] border border-[#3DE8E5]/40" : "text-slate-400 hover:text-slate-200 bg-[#182338]"}`,
                children: opt === "random" ? "\u968F\u673A" : `${opt}\u6B65`
              },
              String(opt)
            );
          }) })
        ] }),
        !isRelayMission && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] text-slate-400 bg-[#080D16] border border-slate-800/80 rounded px-2 py-1 leading-snug", children: missionSpec.capabilityNote })
      ] }),
      !isRelayMission && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "grid grid-cols-2 gap-1 bg-[#080D16] p-0.5 rounded border border-slate-800 shrink-0", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
          "button",
          {
            type: "button",
            onClick: () => setRightTab("AGENT"),
            className: `flex items-center justify-center gap-1 py-1 rounded text-[10.5px] font-semibold transition-colors ${rightTab === "AGENT" ? "bg-[#182338] text-[#3DE8E5] border border-[#3DE8E5]/40" : "text-slate-400 hover:text-slate-200"}`,
            children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Bot, { className: "w-3 h-3" }),
              " Agent / \u51B3\u7B56"
            ]
          }
        ),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
          "button",
          {
            type: "button",
            onClick: () => setRightTab("SKILL"),
            className: `flex items-center justify-center gap-1 py-1 rounded text-[10.5px] font-semibold transition-colors ${rightTab === "SKILL" ? "bg-[#182338] text-[#3DE8E5] border border-[#3DE8E5]/40" : "text-slate-400 hover:text-slate-200"}`,
            children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Layers, { className: "w-3 h-3" }),
              " Skill / \u6267\u884C (",
              completedSteps,
              "/",
              totalSteps,
              ")"
            ]
          }
        )
      ] }),
      isRelayMission && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "order-2 shrink-0 grid grid-cols-2 gap-1.5 border-t border-slate-800/90 pt-1.5", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
          "button",
          {
            type: "button",
            onClick: () => setAgentDrawerOpen((v) => !v),
            className: `flex items-center justify-between gap-1 px-2 py-1 rounded text-[10px] font-semibold border transition-colors ${agentDrawerOpen ? "bg-[#182338] text-[#3DE8E5] border-[#3DE8E5]/40" : "bg-[#080D16] text-slate-400 border-slate-800 hover:text-slate-200"}`,
            children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "flex items-center gap-1 truncate", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Bot, { className: "w-3 h-3 shrink-0" }),
                " Agent / \u51B3\u7B56"
              ] }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: agentDrawerOpen ? "\u6536\u8D77 \u25BE" : "\u5C55\u5F00 \u25B8" })
            ]
          }
        ),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
          "button",
          {
            type: "button",
            onClick: () => setSkillDrawerOpen((v) => !v),
            className: `flex items-center justify-between gap-1 px-2 py-1 rounded text-[10px] font-semibold border transition-colors ${skillDrawerOpen ? "bg-[#182338] text-[#3DE8E5] border-[#3DE8E5]/40" : "bg-[#080D16] text-slate-400 border-slate-800 hover:text-slate-200"}`,
            children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "flex items-center gap-1 truncate", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Layers, { className: "w-3 h-3 shrink-0" }),
                " Skill / \u6267\u884C (",
                completedSteps,
                "/",
                totalSteps,
                ")"
              ] }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: skillDrawerOpen ? "\u6536\u8D77 \u25BE" : "\u5C55\u5F00 \u25B8" })
            ]
          }
        )
      ] }),
      showAgentPanel && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: isRelayMission ? "order-3 max-h-56 shrink-0 overflow-y-auto space-y-2 pr-0.5 text-[11px] border border-slate-800/80 rounded p-1.5 bg-[#0A101B]" : "flex-1 min-h-0 overflow-y-auto space-y-2 pr-0.5 text-[11px]", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: `px-2 py-1.5 rounded border text-[10.5px] font-medium space-y-1 ${plannerBannerStyle}`, children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1.5", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Bot, { className: "w-3.5 h-3.5 shrink-0 text-[#3DE8E5]" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "leading-snug", children: agent?.llm_connected ? `LLM Agent \u5DF2\u8FDE\u63A5 (${agent.llm_model || "Gemini"})` : isVlmPlanner ? agent?.status_label || `Gemini VLM \u672A\u5B8C\u6210\u5728\u7EBF\u9A8C\u8BC1 (${agent?.llm_model || "unconfigured"})` : agent?.planner_mode === "DETERMINISTIC_PLANNER" ? agent.status_label || "\u5F53\u524D\u7531\u786E\u5B9A\u6027\u4EFB\u52A1\u89C4\u5212\u5668\u6267\u884C\uFF0CLLM Agent \u5C1A\u672A\u63A5\u5165" : "Agent \u5C1A\u672A\u63A5\u5165" })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[9.5px] font-mono text-slate-300 flex items-center justify-between gap-1", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: agent?.planner_name || "--" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
              agent?.total_vlm_calls ? `VLM:${agent.total_vlm_calls}\u6B21` : "",
              typeof agent?.model_latency_ms === "number" ? ` \xB7 ${agent.model_latency_ms.toFixed(0)}ms` : ""
            ] })
          ] }),
          agent?.fallback_triggered && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[9.5px] text-[#FFBF69] font-mono", children: [
            "[FALLBACK] \u5DF2\u56DE\u9000\u786E\u5B9A\u6027\u89C4\u5212 (",
            agent.fallback_reason || "VLM_ERROR",
            ")"
          ] })
        ] }),
        isVlmPlanner && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "grid grid-cols-2 gap-1.5", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "rounded border border-[#3DE8E5]/30 bg-[#3DE8E5]/5 p-1.5 space-y-0.5", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[9px] font-mono text-[#3DE8E5]", children: "MODEL A \xB7 VLM PERCEPTION" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] text-slate-200 truncate", children: agent?.perception_model_name || "\u672A\u914D\u7F6E" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[9px] text-slate-500", children: [
              agent?.perception_connected ? "\u5DF2\u9A8C\u8BC1" : "\u672A\u9A8C\u8BC1",
              typeof agent?.perception_latency_ms === "number" ? ` \xB7 ${agent.perception_latency_ms.toFixed(0)}ms` : ""
            ] })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "rounded border border-[#548CFF]/30 bg-[#548CFF]/5 p-1.5 space-y-0.5", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[9px] font-mono text-[#548CFF]", children: "MODEL B \xB7 AGENT PLANNER" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] text-slate-200 truncate", children: agent?.agent_model_name || "\u672A\u914D\u7F6E" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[9px] text-slate-500", children: [
              agent?.agent_connected ? "\u5DF2\u9A8C\u8BC1" : "\u672A\u9A8C\u8BC1",
              typeof agent?.agent_latency_ms === "number" ? ` \xB7 ${agent.agent_latency_ms.toFixed(0)}ms` : ""
            ] })
          ] })
        ] }),
        agent?.latest_semantic_observation && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "rounded border border-slate-800 bg-[#080D16] p-2 space-y-1", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[9.5px] font-mono text-[#3DE8E5]", children: [
            "SEMANTIC OBS \xB7 ",
            agent.latest_semantic_observation.observation_id,
            " \xB7 ",
            agent.latest_semantic_observation.frame_id
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10.5px] text-slate-200", children: agent.latest_semantic_observation.summary }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[10px] text-slate-400", children: [
            "\u5173\u7CFB\uFF1A",
            agent.latest_semantic_observation.cube_relation_to_gripper,
            " \xB7 ",
            agent.latest_semantic_observation.support_relation
          ] }),
          agent.latest_semantic_observation.information_gaps.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[10px] text-[#FFBF69]", children: [
            "\u4FE1\u606F\u7F3A\u53E3\uFF1A",
            agent.latest_semantic_observation.information_gaps.join("\uFF1B")
          ] }),
          agent.latest_semantic_observation.visual_conflicts.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[10px] text-[#FF667B]", children: [
            "\u611F\u77E5\u51B2\u7A81\uFF1A",
            agent.latest_semantic_observation.visual_conflicts.join("\uFF1B")
          ] })
        ] }),
        (mission?.status === "BLOCKED_CAPABILITY" || mission?.blocked_reason || agent?.blocked_or_replan_reason) && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2 rounded bg-[#FFBF69]/10 border border-[#FFBF69]/50 space-y-1", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1.5 text-[#FFBF69] font-semibold text-[11px]", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(TriangleAlert, { className: "w-3.5 h-3.5 shrink-0" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
              "\u80FD\u529B\u963B\u585E \xB7 ",
              mission?.blocked_move ? `\u53D7\u963B\u52A8\u4F5C ${mission.blocked_move}` : "CAPABILITY_BLOCKED"
            ] })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10.5px] text-slate-200 leading-snug", children: mission?.blocked_reason || agent?.blocked_or_replan_reason }),
          mission?.symbolic_solution && mission.symbolic_solution.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[10px] font-mono text-slate-300 bg-[#080D16] px-1.5 py-1 rounded border border-slate-800 break-all", children: [
            "\u7B26\u53F7\u5E8F\u5217 (",
            mission.symbolic_solution.length,
            "\u6B65): ",
            mission.symbolic_solution.join(" ")
          ] })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2 rounded bg-[#080D16] border border-slate-800/90 space-y-1", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between text-[10px] font-mono text-slate-400", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
              "MISSION: ",
              mission?.mission_type || selectedMission
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: mission?.mission_id || "--" })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[10.5px] text-slate-200 leading-snug", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-400", children: "\u76EE\u6807\uFF1A" }),
            mission?.user_goal || missionSpec.shortDesc
          ] }),
          mission?.result_summary && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10.5px] text-[#30D6A0] leading-snug pt-0.5 border-t border-slate-800/80", children: mission.result_summary }),
          mission?.failure_reason && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[10.5px] text-[#FF667B] leading-snug pt-0.5 border-t border-slate-800/80", children: [
            "\u5931\u8D25\u539F\u56E0\uFF1A",
            mission.failure_reason
          ] })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2 rounded bg-[#080D16] border border-slate-800/90 space-y-1.5", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] font-mono text-slate-400", children: "\u6700\u65B0\u89C2\u5BDF\u6458\u8981\u4E0E\u771F\u5B9E\u76F8\u673A\u8F93\u5165" }),
            agent?.current_observation_image_url && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "my-1 rounded overflow-hidden border border-slate-800 bg-black", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                "img",
                {
                  src: agent.current_observation_image_url,
                  alt: agent.current_camera_id || "VLM Input Frame",
                  className: "w-full aspect-[3/2] object-contain"
                }
              ),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "px-1.5 py-0.5 text-[9px] font-mono text-slate-400 flex justify-between", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                  "cam:",
                  agent.current_camera_id || "overhead"
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                  "frm:",
                  agent.current_frame_id || "--"
                ] })
              ] })
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10.5px] text-slate-200 leading-snug", children: agent?.latest_observation ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { children: agent.latest_observation.summary }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[9.5px] font-mono text-slate-500 mt-0.5", children: [
                "obs:",
                agent.latest_observation.observation_id,
                " \xB7 frm:",
                agent.latest_observation.frame_id,
                " \xB7 t=",
                agent.latest_observation.sim_time.toFixed(2),
                "s"
              ] })
            ] }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-500", children: "\u5C1A\u672A\u91C7\u96C6\u89C2\u6D4B\u5E27" }) })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "pt-1 border-t border-slate-800/80 space-y-0.5", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between text-[10px] font-mono text-slate-400", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "\u5F53\u524D\u9009\u62E9\u52A8\u4F5C\u4E0E\u7ED3\u6784\u5316\u4F9D\u636E" }),
              typeof agent?.confidence === "number" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "text-[#3DE8E5]", children: [
                "conf:",
                agent.confidence.toFixed(2)
              ] })
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "font-mono text-[10.5px] text-[#3DE8E5] break-all", children: [
              agent?.selected_action || "--",
              agent?.selected_parameters && Object.keys(agent.selected_parameters).length > 0 ? ` ${JSON.stringify(agent.selected_parameters)}` : ""
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10.5px] text-slate-300 leading-snug mt-0.5", children: agent?.selection_rationale || plan?.rationale_summary || "\u7B49\u5F85\u4EFB\u52A1\u542F\u52A8\u540E\u7531\u89C4\u5212\u5668\u751F\u6210\u51B3\u7B56" }),
            agent?.expected_information_gain && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[9.5px] text-slate-400 leading-snug", children: [
              "\u9884\u671F\u4FE1\u606F\u589E\u76CA\uFF1A",
              agent.expected_information_gain
            ] })
          ] }),
          agent?.safety_gate_status && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "pt-1 border-t border-slate-800/80", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] font-mono text-slate-400", children: "Safety Gate \u6821\u9A8C\u7ED3\u679C" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: `font-mono text-[10px] ${safetyGateStyle}`, children: agent.safety_gate_status })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "pt-1 border-t border-slate-800/80", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] font-mono text-slate-400", children: "\u6700\u8FD1 Skill \u8C03\u7528\u4E0E\u6267\u884C\u53CD\u9988" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "font-mono text-[10px] text-slate-200", children: agent?.last_skill_call || "--" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10.5px] text-slate-400 leading-snug", children: agent?.last_execution_feedback || "--" })
          ] })
        ] }),
        selectedDecisionObservation?.image_url && selectedDecisionObservation.frame_source === "REAL_MUJOCO_RENDERER" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "rounded border border-[#3DE8E5]/30 bg-black overflow-hidden", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "px-2 py-1 text-[9px] font-mono text-[#3DE8E5] bg-[#080D16]", children: [
            "\u5386\u53F2\u51B3\u7B56\u56FE\u50CF \xB7 ",
            selectedDecisionObservation.observation_id,
            " \xB7 ",
            selectedDecisionObservation.frame_id || "--"
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            "img",
            {
              src: selectedDecisionObservation.image_url,
              alt: `Historical observation ${selectedDecisionObservation.observation_id}`,
              className: "w-full max-h-36 object-contain"
            }
          )
        ] }),
        policyTraceEvents.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-1", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] font-mono text-slate-400", children: "ACTIVE SCAN POLICY \xB7 \u786E\u5B9A\u6027\u7B56\u7565\u4F9D\u636E" }),
          policyTraceEvents.slice().reverse().map((event) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-1.5 rounded bg-[#080D16] border border-[#548CFF]/30", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between text-[9.5px] font-mono", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[#548CFF]", children: event.name }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "text-slate-500", children: [
                "t=",
                event.sim_time.toFixed(2),
                "s"
              ] })
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] text-slate-300 mt-0.5", children: String(event.evidence.reason || "") }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[9.5px] text-slate-500 font-mono", children: [
              "unknown=",
              String(event.evidence.remaining_unknown_facelets ?? event.evidence.unknown ?? "--"),
              " \xB7 ",
              "next=",
              String(event.evidence.selected_action ?? "--")
            ] })
          ] }, event.event_id))
        ] }),
        snapshot.relay_state?.enabled && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2 rounded bg-[#080D16] border border-[#548CFF]/40 space-y-1", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[10px] font-mono text-[#3DE8E5] font-semibold flex items-center justify-between", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "EXECUTION CONTRACT & BELIEF \xB7 \u5951\u7EA6\u4E0E\u4FE1\u5FF5\u900F\u89C6" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: snapshot.relay_state.contract.is_lattice_aligned ? "text-[#30D6A0]" : "text-[#FFBF69]", children: snapshot.relay_state.contract.is_lattice_aligned ? "\u6676\u683C\u5BF9\u9F50" : "\u534A\u62E7\u4FDD\u6301" })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[10px] font-mono text-slate-300 space-y-0.5", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
              "\u5B88\u6052\u9501\u5B9A:",
              " ",
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: snapshot.relay_state.belief.deduced_54_unique ? "text-[#30D6A0]" : "text-[#FFBF69]", children: snapshot.relay_state.belief.deduced_54_unique ? "54/54 \u552F\u4E00\u9501\u5B9A" : `\u6B67\u4E49 ${snapshot.relay_state.belief.ambiguous_facelet_count} \u683C` }),
              " \xB7 ",
              "\u89C6\u89C9\u53CD\u63A8: ",
              snapshot.relay_state.belief.inferred_human_moves.join(" ") || "\u65E0"
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
              "\u5951\u7EA6\u6A21\u5F0F: ",
              snapshot.relay_state.contract.active_contract?.mid_turn_recovery_mode || "UNWIND_TO_ZERO",
              " \xB7 ",
              "\u8FC7\u671F\u54CD\u5E94\u62E6\u622A: ",
              snapshot.relay_state.contract.stale_guard?.stale_responses_discarded ?? 0,
              " \u6B21"
            ] }),
            snapshot.relay_state.belief.reasoning_summary_zh && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-slate-400 font-sans text-[10px] leading-snug", children: snapshot.relay_state.belief.reasoning_summary_zh })
          ] })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-1", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[10px] font-mono text-slate-400 flex items-center justify-between", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "DECISION EVENTS \xB7 \u51B3\u7B56\u5BA1\u8BA1\u6D41" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
              decisionEvents.length,
              " \u6761"
            ] })
          ] }),
          decisionEvents.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "p-2 rounded bg-[#080D16] border border-slate-800 text-[10.5px] text-slate-500", children: "\u6682\u65E0\u51B3\u7B56\u4E8B\u4EF6\uFF08\u70B9\u51FB\u5E95\u90E8\u300C\u5F00\u59CB\u4EFB\u52A1\u300D\u6267\u884C\u5F53\u524D Mission\uFF09" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "space-y-1", children: decisionEvents.slice().reverse().map((ev) => {
            const evColor = ev.event_type === "CAPABILITY_BLOCKED" ? "text-[#FFBF69]" : ev.event_type.includes("FAILED") ? "text-[#FF667B]" : "text-[#3DE8E5]";
            const srcColor = ev.source === "gemini_vlm" ? "text-[#30D6A0]" : "text-slate-400";
            return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
              "button",
              {
                type: "button",
                onClick: () => ev.observation_id && setSelectedDecisionObservationId(ev.observation_id),
                className: "w-full text-left p-1.5 rounded bg-[#080D16] border border-slate-800/80 space-y-0.5 hover:border-[#3DE8E5]/40 disabled:cursor-default",
                children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-1 text-[9.5px] font-mono", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: evColor, children: [
                      "#",
                      ev.sequence,
                      " ",
                      ev.event_type
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-500", children: ev.sim_time !== null && ev.sim_time !== void 0 ? `${ev.sim_time.toFixed(2)}s` : ev.wall_time })
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-1 text-[9px] font-mono", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: srcColor, children: [
                      "src:",
                      ev.source
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "text-slate-500", children: [
                      ev.validation_result ? ev.validation_result : "",
                      typeof ev.model_latency_ms === "number" ? ` \xB7 ${ev.model_latency_ms.toFixed(0)}ms` : ""
                    ] })
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10.5px] text-slate-200 leading-snug", children: ev.summary }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] text-slate-400 leading-snug", children: ev.decision_rationale_summary })
                ]
              },
              ev.event_id
            );
          }) })
        ] })
      ] }),
      showSkillPanel && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: isRelayMission ? "order-4 max-h-56 shrink-0 flex flex-col justify-between gap-1.5 overflow-y-auto pr-0.5 border border-slate-800/80 rounded p-1.5 bg-[#0A101B]" : "flex-1 min-h-0 flex flex-col justify-between gap-1.5 overflow-y-auto pr-0.5", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-1 flex-1 overflow-y-auto", children: [
          vlmCompositeTrace && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "px-2 py-1.5 rounded border bg-[#0C1422] border-[#30D6A0]/40 space-y-1 text-[11px]", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
              "button",
              {
                type: "button",
                onClick: () => setExpandedSkills((previous) => {
                  const next = new Set(previous);
                  next.has(vlmCompositeTrace.event_id) ? next.delete(vlmCompositeTrace.event_id) : next.add(vlmCompositeTrace.event_id);
                  return next;
                }),
                className: "w-full flex items-center justify-between text-[10px] font-mono text-[#30D6A0]",
                children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "flex items-center gap-1", children: [
                    expandedSkills.has(vlmCompositeTrace.event_id) ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ChevronDown, { className: "w-3 h-3" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ChevronRight, { className: "w-3 h-3" }),
                    "VLM \u95ED\u73AF\u626B\u63CF Trace \xB7 \u5B50\u4E8B\u4EF6 ",
                    vlmCompositeChildren.length
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: vlmCompositeTrace.status })
                ]
              }
            ),
            expandedSkills.has(vlmCompositeTrace.event_id) && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "ml-1 border-l border-slate-700 pl-2 space-y-1", children: vlmCompositeChildren.map((event) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "rounded border p-1 bg-[#080D16] border-slate-800 text-[9.5px]", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between font-mono", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "text-[#3DE8E5]", children: [
                  event.event_type.toUpperCase(),
                  " ",
                  event.name
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "text-slate-500", children: [
                  event.sim_time.toFixed(2),
                  "s"
                ] })
              ] }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-slate-400", children: [
                "src:",
                event.source,
                " \xB7 ",
                event.status
              ] })
            ] }, event.event_id)) })
          ] }),
          !plan || plan.steps.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "p-2.5 rounded bg-[#080D16] border border-slate-800 text-[11px] text-slate-400", children: isVlmPlanner ? "Gemini VLM \u95ED\u73AF\u6A21\u5F0F\u4E0B\u5C06\u6309\u5B9E\u65F6\u89C6\u89C9\u89C2\u6D4B\u9010\u6B65\u52A8\u6001\u751F\u6210\u52A8\u4F5C\u3002" : "\u5C1A\u672A\u751F\u6210\u4EFB\u52A1\u8BA1\u5212\uFF0C\u8BF7\u9009\u62E9 Mission \u5E76\u542F\u52A8\u4EFB\u52A1\u3002" }) : plan.steps.map((st) => {
            const isCurrent = st.step_id === plan.current_step_id && st.status === "RUNNING";
            const execRec = executions.find((ex) => ex.step_id === st.step_id);
            const composite = traceEvents.find(
              (event) => event.event_type === "composite_skill" && event.skill_id === st.skill_id
            );
            const childEvents = composite ? traceEvents.filter((event) => event.parent_event_id === composite.event_id) : traceEvents.filter(
              (event) => event.skill_id === st.skill_id && event.event_type !== "composite_skill" && event.event_type !== "mission"
            );
            const hasChildren = Boolean(composite) || childEvents.length > 0;
            const skillExpanded = expandedSkills.has(st.step_id);
            return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
              "div",
              {
                className: `px-2 py-1.5 rounded border space-y-1 text-[11px] ${isCurrent ? "bg-[#182338] border-[#548CFF]/60" : st.status === "BLOCKED" ? "bg-[#FFBF69]/10 border-[#FFBF69]/50" : "bg-[#080D16] border-slate-800/80"}`,
                children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-1.5", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "min-w-0 flex-1", children: [
                      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1.5", children: [
                        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "font-mono text-[10px] text-slate-500", children: [
                          "0",
                          st.index
                        ] }),
                        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "font-medium text-slate-200 truncate", children: st.title })
                      ] }),
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "font-mono text-[9.5px] text-[#3DE8E5] pl-5 truncate", children: st.skill_id })
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1 shrink-0", children: [
                      st.elapsed_sec !== null && st.elapsed_sec !== void 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "font-mono text-[9.5px] text-slate-400", children: [
                        st.elapsed_sec.toFixed(2),
                        "s"
                      ] }),
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(StageStatusBadge, { status: st.status, implemented: st.implemented })
                    ] })
                  ] }),
                  st.started_sim_time !== null && st.started_sim_time !== void 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[9.5px] font-mono text-slate-500 pl-5", children: [
                    "sim: ",
                    st.started_sim_time.toFixed(2),
                    "s \u2192",
                    " ",
                    st.ended_sim_time !== null && st.ended_sim_time !== void 0 ? `${st.ended_sim_time.toFixed(2)}s` : "..."
                  ] }),
                  (st.result_summary || execRec?.result_summary) && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] text-slate-300 pl-5 leading-snug", children: st.result_summary || execRec?.result_summary }),
                  st.failure_reason && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[10px] text-[#FF667B] pl-5 leading-snug", children: [
                    "\u539F\u56E0: ",
                    st.failure_reason
                  ] }),
                  hasChildren && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "pl-5 pt-0.5", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
                      "button",
                      {
                        type: "button",
                        onClick: () => setExpandedSkills((previous) => {
                          const next = new Set(previous);
                          next.has(st.step_id) ? next.delete(st.step_id) : next.add(st.step_id);
                          return next;
                        }),
                        className: "flex items-center gap-1 text-[10px] font-mono text-[#3DE8E5] hover:text-white",
                        children: [
                          skillExpanded ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ChevronDown, { className: "w-3 h-3" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ChevronRight, { className: "w-3 h-3" }),
                          "\u5B50\u4E8B\u4EF6 ",
                          childEvents.length,
                          " \xB7 ",
                          composite ? composite.status : st.status
                        ]
                      }
                    ),
                    skillExpanded && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "mt-1 ml-1 border-l border-slate-700 pl-2 space-y-1", children: childEvents.map((event) => {
                      const eventExpanded = expandedTraceEvents.has(event.event_id);
                      const eventFailed = event.status === "FAILED";
                      const evidence = event.evidence || {};
                      const target = evidence.target_parameters || {};
                      const measured = evidence.measured_parameters || {};
                      return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: `rounded border p-1.5 ${eventFailed ? "bg-[#FF667B]/10 border-[#FF667B]/40" : "bg-[#0C1422] border-slate-800"}`, children: [
                        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
                          "button",
                          {
                            type: "button",
                            onClick: () => setExpandedTraceEvents((previous) => {
                              const next = new Set(previous);
                              next.has(event.event_id) ? next.delete(event.event_id) : next.add(event.event_id);
                              return next;
                            }),
                            className: "w-full text-left",
                            children: [
                              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-1", children: [
                                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "flex items-center gap-1 font-mono text-[9.5px] text-slate-200", children: [
                                  eventExpanded ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ChevronDown, { className: "w-3 h-3" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ChevronRight, { className: "w-3 h-3" }),
                                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: event.event_type === "perception" ? "text-[#3DE8E5]" : event.event_type === "decision" ? "text-[#548CFF]" : event.event_type === "verification" ? "text-[#30D6A0]" : "text-[#FFBF69]", children: event.event_type.toUpperCase() }),
                                  event.name
                                ] }),
                                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "font-mono text-[9px] text-slate-500", children: [
                                  event.sim_time.toFixed(2),
                                  "\u2192",
                                  (event.end_sim_time ?? event.sim_time).toFixed(2),
                                  "s"
                                ] })
                              ] }),
                              event.event_type === "perception" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[9.5px] text-slate-400 pl-4 mt-0.5", children: [
                                (evidence.camera_ids || []).join(", ") || "\u65E0\u6709\u6548\u76F8\u673A",
                                " \xB7 \u65B0\u589E ",
                                String(evidence.newly_observed ?? 0),
                                " \u683C \xB7 Unknown ",
                                String(evidence.unknown_before),
                                "\u2192",
                                String(evidence.unknown_after),
                                " \xB7 \u51B2\u7A81 ",
                                String(evidence.conflicts ?? 0)
                              ] }),
                              event.event_type === "action" && event.name.includes("reorient") && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[9.5px] text-slate-400 pl-4 mt-0.5", children: [
                                String(target.axis || "--"),
                                " \xB7 \u76EE\u6807 ",
                                typeof target.degrees === "number" ? target.degrees.toFixed(1) : "--",
                                "\xB0 \xB7 \u5B9E\u6D4B ",
                                typeof measured.degrees === "number" ? measured.degrees.toFixed(1) : "--",
                                "\xB0"
                              ] })
                            ]
                          }
                        ),
                        eventExpanded && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "mt-1 pl-4 space-y-1 text-[9.5px] text-slate-400", children: [
                          event.event_type === "perception" && evidence.camera_contributions && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "font-mono", children: Object.entries(evidence.camera_contributions).map(([camera, indices]) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
                            camera,
                            ": [",
                            indices.join(", "),
                            "]"
                          ] }, camera)) }),
                          Array.isArray(evidence.frame_images) && evidence.frame_images.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "grid grid-cols-2 gap-1", children: evidence.frame_images.map((frame) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("figure", { className: "bg-black/30 rounded overflow-hidden border border-slate-800", children: [
                            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("img", { src: frame.image_url, alt: frame.camera_id, className: "w-full aspect-[3/2] object-contain" }),
                            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("figcaption", { className: "px-1 py-0.5 truncate font-mono text-[8.5px]", children: frame.camera_id })
                          ] }, frame.frame_ref)) }),
                          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("details", { children: [
                            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("summary", { className: "cursor-pointer text-slate-500", children: "\u8BE6\u7EC6\u53C2\u6570" }),
                            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("pre", { className: "mt-1 p-1 rounded bg-black/20 overflow-x-auto whitespace-pre-wrap break-all text-[8.5px]", children: JSON.stringify(evidence, null, 2) })
                          ] })
                        ] })
                      ] }, event.event_id);
                    }) })
                  ] })
                ]
              },
              st.step_id
            );
          })
        ] }),
        snapshot.physical_verification && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2 rounded bg-[#080D16] border border-[#30D6A0]/30 text-[10px] font-mono space-y-0.5 shrink-0", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[#30D6A0] font-semibold", children: "\u7269\u7406\u63A5\u89E6\u4E0E\u89C6\u89C9\u590D\u6838\u8BC1\u636E" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-slate-300", children: [
            "\u5B9E\u6D4B\u8F6C\u89D2: ",
            String(snapshot.physical_verification.actual_angle_deg ?? "--"),
            "\xB0 \xB7 \u8BEF\u5DEE:",
            " ",
            typeof snapshot.physical_verification.layer_error_rad === "number" ? snapshot.physical_verification.layer_error_rad.toExponential(2) : "--",
            " ",
            "rad"
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-slate-300", children: [
            "\u63A5\u89E6\u529B(\u5E95\u5EA7/\u62E7\u5934): ",
            String(snapshot.physical_verification.min_base_contact_n ?? "--"),
            "N /",
            " ",
            String(snapshot.physical_verification.min_turn_contact_n ?? "--"),
            "N \xB7 21\u683C:",
            " ",
            snapshot.physical_verification.affected_21_verified ? "VERIFIED" : "PENDING"
          ] })
        ] })
      ] }),
      isRelayMission && (() => {
        const relay = snapshot.relay_state;
        const waitingHuman = Boolean(relay?.human_pad?.waiting_for_human);
        const padActive = Boolean(relay?.human_pad?.active) && mode === "LIVE";
        const suggested = relay?.delegation?.suggested_moves || [];
        const prefDone = relay?.delegation?.completed_prefix_count || 0;
        const deviated = Boolean(relay?.delegation?.deviated_this_turn);
        const nextHint = relay?.human_pad?.highlighted_next_move;
        const clarPending = Boolean(relay?.hri?.clarification_pending);
        const clicks = relay?.human_pad?.clicks_this_turn || [];
        const dialog = relay?.hri?.dialog_history || [];
        const turnInfo = relay?.turn_indicator;
        const owner = turnInfo?.owner || (waitingHuman ? "HUMAN" : clarPending ? "CLARIFY" : relay?.phase === "RELAY_COMPLETED_VERIFIED" ? "DONE" : snapshot.running ? "ROBOT" : "IDLE");
        const rightTurnCls = owner === "HUMAN" ? "bg-[#FFBF69]/15 border-[#FFBF69]/60 text-[#FFBF69]" : owner === "CLARIFY" ? "bg-[#8B5CF6]/15 border-[#8B5CF6]/50 text-[#A78BFA]" : owner === "DONE" ? "bg-[#30D6A0]/15 border-[#30D6A0]/50 text-[#30D6A0]" : owner === "ROBOT" ? "bg-[#3DE8E5]/10 border-[#3DE8E5]/40 text-[#3DE8E5]" : "bg-[#080D16] border-slate-800 text-slate-300";
        const applyPerturb = (dxCm, dyCm, dyawDeg, label) => {
          setPerturbDxCm(dxCm);
          setPerturbDyCm(dyCm);
          setPerturbYawDeg(dyawDeg);
          onRelayCommand(
            { type: "HUMAN_PERTURB_POSE", dx_m: dxCm / 100, dy_m: dyCm / 100, dyaw_deg: dyawDeg },
            label
          );
        };
        const sendChat = (text) => {
          const clean = text.trim();
          if (!clean) return;
          onRelayCommand({ type: "HUMAN_SEND_CHAT", text: clean }, `\u53D1\u9001\u6307\u4EE4: ${clean}`);
          setChatDraft("");
        };
        return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "order-1 flex-1 min-h-0 overflow-y-auto space-y-2 pr-0.5 text-[11px]", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: `p-2 rounded border space-y-1 ${rightTurnCls}`, children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-2 text-[11px] font-bold", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: turnInfo?.owner_label_zh || (waitingHuman ? "\u{1F9D1} \u8F6E\u5230\u4EBA\u7C7B\u64CD\u4F5C" : "\u{1F916} \u7B49\u5F85/\u673A\u5668\u4EBA\u56DE\u5408") }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "font-mono text-[10px]", children: [
                "\u7B2C ",
                relay?.round_number || 1,
                " \u8F6E"
              ] })
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { className: "flex items-center justify-between gap-2", children: [
              "\u672C\u56DE\u5408\u673A\u5668\u4EBA\u6B65\u6570\u914D\u989D: ",
              relay?.robot_moves_this_turn ?? 0,
              " / ",
              relay?.max_robot_moves_per_turn === null ? "\u221E" : relay?.max_robot_moves_per_turn ?? 3,
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
                "select",
                {
                  "aria-label": "\u6BCF\u56DE\u5408\u673A\u5668\u4EBA\u6B65\u6570",
                  className: "rounded bg-[#080D16] border border-slate-700",
                  value: relay?.max_robot_moves_per_turn === null ? "unlimited" : relay?.max_robot_moves_per_turn ?? 3,
                  onChange: (e) => onRelayCommand({ type: "SET_TURN_QUOTA", quota: e.target.value === "unlimited" ? "unlimited" : Number(e.target.value) }, "\u8BBE\u7F6E\u56DE\u5408\u914D\u989D"),
                  children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "1", children: "1 \u6B65" }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "2", children: "2 \u6B65" }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "3", children: "3 \u6B65" }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "unlimited", children: "\u5168\u6258\u7BA1" })
                  ]
                }
              )
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] opacity-85 leading-snug", children: turnInfo?.next_action_hint_zh || relay?.banner?.subtitle_zh || "\u7B49\u5F85\u4EFB\u52A1\u542F\u52A8\u3002" })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2 rounded bg-[#080D16] border border-[#3DE8E5]/30 space-y-1.5", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-1 text-[10px] font-mono", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[#3DE8E5] font-semibold", children: "AGENT DELEGATION \xB7 \u63A8\u8350\u63A5\u529B\u5E8F\u5217" }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "text-slate-400", children: [
                "\u5DF2\u7701\u9AD8\u4EE3\u4EF7\u7FFB\u9762 ",
                relay?.delegation?.saved_high_cost_flips_count ?? 0,
                " \u6B21"
              ] })
            ] }),
            suggested.length > 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "flex items-center gap-1 flex-wrap", children: suggested.map((mv, idx) => {
              const done = idx < prefDone && !deviated;
              const isNext = idx === prefDone && !deviated && waitingHuman;
              return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
                "span",
                {
                  className: `px-2 py-0.5 rounded font-mono text-[10.5px] border ${done ? "bg-[#30D6A0]/15 text-[#30D6A0] border-[#30D6A0]/40" : isNext ? "bg-[#FFBF69]/20 text-[#FFBF69] border-[#FFBF69]/60 animate-pulse" : "bg-[#182338] text-slate-300 border-slate-700"}`,
                  children: [
                    done ? "\u2713 " : `Step ${idx + 1}: `,
                    mv
                  ]
                },
                `${mv}-${idx}`
              );
            }) }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] text-slate-400", children: "\u5F53\u524D\u65E0\u5F3A\u5236\u63A8\u8350\u5E8F\u5217\uFF08\u53EF\u81EA\u7531\u70B9\u51FB\u4E0B\u65B9 18 \u52A8\u4F5C\u6216\u53D1\u9001\u81EA\u7136\u8BED\u8A00\u8981\u6C42\uFF09\u3002" }),
            deviated && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "px-2 py-1 rounded bg-[#FFBF69]/15 border border-[#FFBF69]/40 text-[10px] text-[#FFBF69]", children: "\u26A1 \u68C0\u6D4B\u5230\u81EA\u7531\u53D1\u6325/\u504F\u79BB\u63A8\u8350\u8DEF\u7EBF\uFF0C\u4EA4\u56DE\u540E Agent \u5C06\u9760 RGB-D \u91CD\u65B0\u8BC6\u522B\u5E76\u51B3\u5B9A\u7B56\u7565" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] text-slate-300 leading-snug", children: relay?.delegation?.delegation_reason_zh || "\u7B49\u5F85 Agent \u5B8C\u6210\u611F\u77E5\u5EFA\u4FE1\u5E76\u751F\u6210\u5177\u8EAB\u4EE3\u4EF7\u5207\u5206\u5EFA\u8BAE\u3002" })
          ] }),
          clarPending && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2 rounded bg-[#FFBF69]/10 border border-[#FFBF69]/50 space-y-1.5", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10.5px] font-semibold text-[#FFBF69]", children: "\u{1F4AC} Agent \u8BF7\u6C42\u610F\u56FE\u6F84\u6E05" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10.5px] text-slate-200 leading-snug", children: relay?.hri?.clarification_question_zh }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "flex flex-col gap-1", children: (relay?.hri?.clarification_options || []).map((opt) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
              "button",
              {
                type: "button",
                disabled: mode !== "LIVE",
                onClick: () => sendChat(opt),
                className: "text-left px-2 py-1 rounded text-[10px] bg-[#182338] hover:bg-[#548CFF]/20 text-[#3DE8E5] border border-[#3DE8E5]/30 transition-colors disabled:opacity-40",
                children: [
                  "\u2192 ",
                  opt
                ]
              },
              opt
            )) })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2 rounded bg-[#080D16] border border-slate-800 space-y-1.5", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-1 text-[10px]", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "font-mono text-slate-300 font-semibold", children: "18-MOVE PAD \xB7 26-Cubie \u771F\u5B9E\u7269\u7406\u8F6C\u5C42" }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                "button",
                {
                  type: "button",
                  disabled: !padActive || !relay?.human_pad?.can_undo,
                  onClick: () => onRelayCommand({ type: "HUMAN_UNDO_MOVE" }, "\u7269\u7406\u64A4\u9500\u4E0A\u4E00\u6B65"),
                  className: "px-1.5 py-0.5 rounded bg-[#182338] text-slate-300 border border-slate-700 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed text-[9.5px]",
                  children: "\u64A4\u9500\u4E0A\u4E00\u6B65"
                }
              )
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "space-y-1", children: RELAY_FACE_GROUPS.map((grp) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "grid grid-cols-3 gap-1", children: grp.moves.map((mv) => {
              const isHint = nextHint === mv && waitingHuman;
              return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                "button",
                {
                  type: "button",
                  disabled: !padActive,
                  onClick: () => onRelayCommand({ type: "HUMAN_APPLY_MOVE", move: mv }, `\u4EBA\u7C7B\u7269\u7406\u65CB\u8F6C ${mv}`),
                  className: `py-1 rounded font-mono text-[10.5px] font-semibold border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${isHint ? "bg-[#3DE8E5]/20 text-[#3DE8E5] border-[#3DE8E5] animate-pulse" : "bg-[#182338] hover:bg-[#548CFF]/30 text-slate-200 border-slate-700"}`,
                  children: mv
                },
                mv
              );
            }) }, grp.face)) }),
            clicks.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[10px] font-mono text-slate-400", children: [
              "\u672C\u8F6E\u5DF2\u62E7: ",
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[#3DE8E5]", children: clicks.join(" \u2192 ") })
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "button",
              {
                type: "button",
                disabled: !waitingHuman || mode !== "LIVE",
                onClick: () => onRelayCommand({ type: "HUMAN_FINISH_TURN" }, "\u5B8C\u6210\u672C\u56DE\u5408\uFF0C\u4EA4\u56DE\u673A\u5668\u4EBA"),
                className: "w-full py-1.5 rounded text-[11px] font-semibold bg-[#30D6A0]/20 hover:bg-[#30D6A0]/30 text-[#30D6A0] border border-[#30D6A0]/50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
                children: "\u5B8C\u6210\u672C\u56DE\u5408\uFF0C\u4EA4\u56DE\u673A\u5668\u4EBA"
              }
            )
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2 rounded bg-[#080D16] border border-slate-800 space-y-1.5", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between text-[10px] font-mono text-slate-300", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "PUT-BACK PERTURB \xB7 \u653E\u56DE\u684C\u9762\u4F4D\u7F6E\u5FAE\u6270" }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "text-[#FFBF69]", children: [
                perturbDxCm >= 0 ? `+${perturbDxCm}` : perturbDxCm,
                "cm,",
                " ",
                perturbDyCm >= 0 ? `+${perturbDyCm}` : perturbDyCm,
                "cm,",
                " ",
                perturbYawDeg >= 0 ? `+${perturbYawDeg}` : perturbYawDeg,
                "\xB0"
              ] })
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-1 text-[10px] font-mono text-slate-400", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-2", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "w-16", children: "\u0394X (\xB18cm)" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                  "input",
                  {
                    type: "range",
                    min: -8,
                    max: 8,
                    step: 1,
                    disabled: !padActive,
                    value: perturbDxCm,
                    onChange: (e) => setPerturbDxCm(Number(e.target.value)),
                    onMouseUp: () => applyPerturb(perturbDxCm, perturbDyCm, perturbYawDeg, "\u8C03\u6574 \u0394X \u5FAE\u6270"),
                    onTouchEnd: () => applyPerturb(perturbDxCm, perturbDyCm, perturbYawDeg, "\u8C03\u6574 \u0394X \u5FAE\u6270"),
                    className: "flex-1"
                  }
                )
              ] }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-2", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "w-16", children: "\u0394Y (\xB18cm)" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                  "input",
                  {
                    type: "range",
                    min: -8,
                    max: 8,
                    step: 1,
                    disabled: !padActive,
                    value: perturbDyCm,
                    onChange: (e) => setPerturbDyCm(Number(e.target.value)),
                    onMouseUp: () => applyPerturb(perturbDxCm, perturbDyCm, perturbYawDeg, "\u8C03\u6574 \u0394Y \u5FAE\u6270"),
                    onTouchEnd: () => applyPerturb(perturbDxCm, perturbDyCm, perturbYawDeg, "\u8C03\u6574 \u0394Y \u5FAE\u6270"),
                    className: "flex-1"
                  }
                )
              ] }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-2", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "w-16", children: "\u0394Yaw(\xB140\xB0)" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                  "input",
                  {
                    type: "range",
                    min: -40,
                    max: 40,
                    step: 1,
                    disabled: !padActive,
                    value: perturbYawDeg,
                    onChange: (e) => setPerturbYawDeg(Number(e.target.value)),
                    onMouseUp: () => applyPerturb(perturbDxCm, perturbDyCm, perturbYawDeg, "\u8C03\u6574 \u0394Yaw \u5FAE\u6270"),
                    onTouchEnd: () => applyPerturb(perturbDxCm, perturbDyCm, perturbYawDeg, "\u8C03\u6574 \u0394Yaw \u5FAE\u6270"),
                    className: "flex-1"
                  }
                )
              ] })
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "grid grid-cols-2 gap-1 text-[9.5px]", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                "button",
                {
                  type: "button",
                  disabled: !padActive,
                  onClick: () => applyPerturb(0, 0, 0, "\u9884\u8BBE: \u6807\u51C6\u539F\u4F4D"),
                  className: "px-1.5 py-1 rounded bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700 disabled:opacity-40",
                  children: "\u6807\u51C6\u539F\u4F4D"
                }
              ),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                "button",
                {
                  type: "button",
                  disabled: !padActive,
                  onClick: () => applyPerturb(4, 0, 15, "\u9884\u8BBE: \u8F7B\u63A8\u504F\u79FB"),
                  className: "px-1.5 py-1 rounded bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700 disabled:opacity-40",
                  children: "\u8F7B\u63A8\u504F\u79FB (+4cm,+15\xB0)"
                }
              ),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                "button",
                {
                  type: "button",
                  disabled: !padActive,
                  onClick: () => applyPerturb(6, -4, 20, "\u9884\u8BBE: \u8DE8\u5EA6\u5FAE\u6270"),
                  className: "px-1.5 py-1 rounded bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700 disabled:opacity-40",
                  children: "\u8DE8\u5EA6\u5FAE\u6270 (+6cm,-4cm,+20\xB0)"
                }
              ),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                "button",
                {
                  type: "button",
                  disabled: !padActive,
                  onClick: () => {
                    const rx = Math.round(Math.random() * 16 - 8);
                    const ry = Math.round(Math.random() * 16 - 8);
                    const ryaw = Math.round(Math.random() * 76 - 38);
                    applyPerturb(rx, ry, ryaw, "\u9884\u8BBE: \u968F\u673A\u968F\u624B\u653E");
                  },
                  className: "px-1.5 py-1 rounded bg-[#182338] hover:bg-slate-700 text-[#FFBF69] border border-slate-700 disabled:opacity-40",
                  children: "\u968F\u673A\u968F\u624B\u653E"
                }
              )
            ] })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2 rounded bg-[#080D16] border border-slate-800 space-y-1.5", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-1 text-[10px] font-mono", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[#3DE8E5] font-semibold", children: "LIVE HRI DIALOG \xB7 LLM \u8BED\u4E49\u610F\u56FE\u8DEF\u7531" }),
              relay?.hri?.latest_semantics && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "px-1.5 py-0.5 rounded bg-[#182338] border border-slate-700 text-[9px] text-[#30D6A0] truncate", children: [
                relay.hri.latest_semantics.speech_act,
                typeof relay.hri.latest_semantics.latency_ms === "number" ? ` \xB7 ${relay.hri.latest_semantics.latency_ms.toFixed(0)}ms` : ""
              ] })
            ] }),
            (relay?.hri?.active_constraints || []).length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1 flex-wrap text-[9px]", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-400 font-mono", children: "\u6301\u4E45\u7EA6\u675F:" }),
              (relay?.hri?.active_constraints || []).map((c, idx) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                "span",
                {
                  className: "px-1.5 py-0.5 rounded bg-[#30D6A0]/10 border border-[#30D6A0]/30 text-[#30D6A0]",
                  children: c
                },
                `${c}-${idx}`
              ))
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "max-h-36 overflow-y-auto space-y-1 bg-[#0C1422] border border-slate-800/70 rounded p-1.5", children: dialog.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] text-slate-500", children: "\u968F\u65F6\u53EF\u53D1\u9001\u504F\u597D\u7EA6\u675F\u3001\u6F84\u6E05\u56DE\u590D\u6216\u673A\u68B0\u81C2\u6267\u884C\u4E2D\u9014\u7D27\u6025\u5239\u8F66\u6307\u4EE4\u3002" }) : dialog.map((msg, i) => {
              const isHumanMsg = msg.role === "human";
              const sem = msg.semantics;
              const bubbleCls = isHumanMsg ? "bg-[#548CFF]/15 text-slate-100 border border-[#548CFF]/30" : "bg-[#182338] text-[#3DE8E5] border border-slate-700";
              return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
                "div",
                {
                  className: `px-1.5 py-1 rounded text-[10px] leading-snug space-y-0.5 ${bubbleCls}`,
                  children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "font-mono font-semibold mr-1", children: isHumanMsg ? "\u{1F9D1} \u4EBA\u7C7B:" : "\u{1F916} Agent:" }),
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: msg.text })
                    ] }),
                    isHumanMsg && sem && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1 flex-wrap text-[9px] font-mono text-slate-300 pt-0.5 border-t border-slate-700/60", children: [
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "px-1 py-0.2 rounded bg-[#080D16] border border-[#3DE8E5]/40 text-[#3DE8E5]", children: sem.speech_act }),
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                        "span",
                        {
                          className: `px-1 py-0.2 rounded border ${sem.requires_immediate_motion_interrupt ? "bg-[#FF667B]/15 border-[#FF667B]/40 text-[#FF667B]" : "bg-[#30D6A0]/10 border-[#30D6A0]/30 text-[#30D6A0]"}`,
                          children: sem.requires_immediate_motion_interrupt ? "\u26A1\u7ACB\u5373\u4E2D\u65AD" : "\u5E73\u6ED1\u4E0D\u4E2D\u65AD"
                        }
                      ),
                      typeof sem.latency_ms === "number" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "text-slate-400", children: [
                        sem.latency_ms.toFixed(0),
                        "ms"
                      ] }),
                      sem.persistent_constraints_to_add && sem.persistent_constraints_to_add.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "text-[#FFBF69]", children: [
                        "+\u7EA6\u675F: ",
                        sem.persistent_constraints_to_add.join("\uFF1B")
                      ] })
                    ] })
                  ]
                },
                i
              );
            }) }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                "input",
                {
                  type: "text",
                  value: chatDraft,
                  onChange: (e) => setChatDraft(e.target.value),
                  onKeyDown: (e) => {
                    if (e.key === "Enter") sendChat(chatDraft);
                  },
                  placeholder: "\u8F93\u5165\u4E2D\u6587\u7EA6\u675F/\u610F\u56FE/\u5B9E\u65F6\u6253\u65AD\u6307\u4EE4...",
                  disabled: mode !== "LIVE",
                  className: "flex-1 rounded border border-slate-700 bg-[#0C1422] px-2 py-1 text-[10.5px] text-slate-100 placeholder:text-slate-600 outline-none focus:border-[#30D6A0]"
                }
              ),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                "button",
                {
                  type: "button",
                  disabled: mode !== "LIVE" || !chatDraft.trim(),
                  onClick: () => sendChat(chatDraft),
                  className: "px-2 py-1 rounded text-[10.5px] font-semibold bg-[#548CFF] text-white disabled:opacity-40",
                  children: "\u53D1\u9001"
                }
              )
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "flex items-center gap-1 flex-wrap", children: QUICK_HRI_CHIPS.map((chip) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "button",
              {
                type: "button",
                disabled: mode !== "LIVE",
                title: chip.text,
                onClick: () => sendChat(chip.text),
                className: "px-1.5 py-0.5 rounded text-[9.5px] bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700 disabled:opacity-40",
                children: chip.label
              },
              chip.label
            )) })
          ] })
        ] });
      })()
    ] });
  };
  var CompactRobotCameraCard = ({ rgbUrl, depthUrl, depthRangeM, detections }) => {
    const [sensorMode, setSensorMode] = (0, import_react3.useState)("RGB");
    const [showOverlay, setShowOverlay] = (0, import_react3.useState)(true);
    const activeUrl = sensorMode === "RGB" ? rgbUrl : depthUrl;
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#101827] border border-slate-800/90 rounded-lg p-2.5 flex flex-col justify-between h-full min-h-0", children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-1.5 mb-1.5 shrink-0", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1.5 min-w-0", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Camera, { className: "w-3.5 h-3.5 text-[#3DE8E5] shrink-0" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[11px] font-semibold tracking-wider text-slate-200 uppercase truncate", children: "ROBOT CAMERA \xB7 \u673A\u5668\u4EBA\u76F8\u673A" })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1 shrink-0", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            "button",
            {
              type: "button",
              onClick: () => setShowOverlay((v) => !v),
              className: `px-1.5 py-0.5 rounded text-[10px] border transition-colors ${showOverlay ? "bg-[#3DE8E5]/15 text-[#3DE8E5] border-[#3DE8E5]/40" : "bg-[#182338] text-slate-400 border-slate-700"}`,
              children: "\u68C0\u6D4B\u6846"
            }
          ),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex rounded bg-[#080D16] p-0.5 border border-slate-800 text-[10px] font-mono", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "button",
              {
                type: "button",
                onClick: () => setSensorMode("RGB"),
                className: `px-1.5 py-0.2 rounded ${sensorMode === "RGB" ? "bg-[#548CFF] text-white" : "text-slate-400"}`,
                children: "RGB"
              }
            ),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "button",
              {
                type: "button",
                onClick: () => setSensorMode("DEPTH"),
                className: `px-1.5 py-0.2 rounded ${sensorMode === "DEPTH" ? "bg-[#548CFF] text-white" : "text-slate-400"}`,
                children: "Depth"
              }
            )
          ] })
        ] })
      ] }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "relative flex-1 min-h-0 w-full rounded bg-[#080D16] border border-slate-800 overflow-hidden flex items-center justify-center", children: activeUrl ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("img", { src: activeUrl, alt: sensorMode, className: "w-full h-full object-contain" }),
        showOverlay && detections.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
          "svg",
          {
            viewBox: "0 0 100 100",
            preserveAspectRatio: "none",
            className: "absolute inset-0 w-full h-full pointer-events-none",
            children: detections.map((box) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("g", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "rect",
              {
                x: box.xNorm * 100,
                y: box.yNorm * 100,
                width: box.wNorm * 100,
                height: box.hNorm * 100,
                fill: "none",
                stroke: "#3DE8E5",
                strokeWidth: "0.65"
              }
            ) }, box.id))
          }
        )
      ] }) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-center px-2 space-y-1", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Scan, { className: "w-4 h-4 mx-auto text-slate-500" }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[11px] text-slate-400", children: "\u76F8\u673A\u6570\u636E\u4E0D\u53EF\u7528" })
      ] }) }),
      sensorMode === "DEPTH" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-2 pt-1 text-[10px] font-mono text-slate-400 shrink-0", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
          depthRangeM[0].toFixed(2),
          "m"
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
          "div",
          {
            className: "flex-1 h-1.5 rounded border border-slate-700",
            style: {
              background: "linear-gradient(to right, #0f172a, #1d4ed8, #06b6d4, #22c55e, #eab308, #ef4444)"
            }
          }
        ),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
          depthRangeM[1].toFixed(2),
          "m"
        ] })
      ] })
    ] });
  };
  var CompactCubeStateCard = ({ observed, predicted, validationStatus }) => {
    const [viewTab, setViewTab] = (0, import_react3.useState)("OBSERVED");
    const stats = (0, import_react3.useMemo)(() => {
      let observedCount = 0;
      let unknownCount = 0;
      let conflictCount = 0;
      let mismatchCount = 0;
      observed.forEach((cell, idx) => {
        if (cell.color === "UNKNOWN") {
          unknownCount++;
        } else {
          observedCount++;
          const pred = predicted[idx];
          if (pred && pred !== "UNKNOWN" && pred !== cell.color) {
            mismatchCount++;
          }
        }
        if (cell.hasConflict) conflictCount++;
      });
      return { observedCount, unknownCount, conflictCount, mismatchCount };
    }, [observed, predicted]);
    const netLayout = [
      { face: "U", row: 0, col: 1 },
      { face: "L", row: 1, col: 0 },
      { face: "F", row: 1, col: 1 },
      { face: "R", row: 1, col: 2 },
      { face: "B", row: 1, col: 3 },
      { face: "D", row: 2, col: 1 }
    ];
    const renderFace = (face) => {
      const baseIdx = FACE_ORDER.indexOf(face) * 9;
      return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "grid grid-cols-3 gap-[1.5px] p-[2px] rounded bg-[#080D16] border border-slate-800", children: Array.from({ length: 9 }).map((_, localIdx) => {
        const globalIdx = baseIdx + localIdx;
        const obs = observed[globalIdx] || { color: "UNKNOWN" };
        const pred = predicted[globalIdx] || "UNKNOWN";
        let displayColor = "UNKNOWN";
        let isMismatch = false;
        if (viewTab === "OBSERVED") {
          displayColor = obs.color;
        } else if (viewTab === "PREDICTED") {
          displayColor = pred;
        } else {
          if (obs.color === "UNKNOWN") {
            displayColor = "UNKNOWN";
          } else {
            displayColor = obs.color;
            isMismatch = pred !== "UNKNOWN" && pred !== obs.color;
          }
        }
        const style = COLOR_MAP[displayColor];
        return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
          "div",
          {
            title: `${face}${localIdx} | \u5B9E\u6D4B:${obs.color} | \u9884\u6D4B:${pred}`,
            style: {
              backgroundColor: style.bg,
              borderColor: isMismatch ? "#FF667B" : style.border,
              color: style.text
            },
            className: "w-3.5 h-3.5 rounded-[1.5px] border flex items-center justify-center text-[8px] font-mono font-bold leading-none",
            children: displayColor === "UNKNOWN" ? "?" : localIdx === 4 ? face : ""
          },
          localIdx
        );
      }) }, face);
    };
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#101827] border border-slate-800/90 rounded-lg p-2.5 flex flex-col justify-between h-full min-h-0", children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-1.5 shrink-0", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1.5 min-w-0", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Grid3x3, { className: "w-3.5 h-3.5 text-[#3DE8E5] shrink-0" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "text-[11px] font-semibold tracking-wider text-slate-200 uppercase truncate", children: [
            "CUBE STATE \xB7 ",
            stats.observedCount,
            "/54"
          ] })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex rounded bg-[#080D16] p-0.5 border border-slate-800 text-[10px] shrink-0", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            "button",
            {
              type: "button",
              onClick: () => setViewTab("OBSERVED"),
              className: `px-1.5 py-0.2 rounded ${viewTab === "OBSERVED" ? "bg-[#548CFF] text-white" : "text-slate-400"}`,
              children: "\u5B9E\u6D4B"
            }
          ),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            "button",
            {
              type: "button",
              onClick: () => setViewTab("PREDICTED"),
              className: `px-1.5 py-0.2 rounded ${viewTab === "PREDICTED" ? "bg-[#548CFF] text-white" : "text-slate-400"}`,
              children: "\u9884\u6D4B"
            }
          ),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            "button",
            {
              type: "button",
              onClick: () => setViewTab("COMPARISON"),
              className: `px-1.5 py-0.2 rounded ${viewTab === "COMPARISON" ? "bg-[#548CFF] text-white" : "text-slate-400"}`,
              children: "\u5BF9\u6BD4"
            }
          )
        ] })
      ] }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "flex-1 flex items-center justify-center min-h-0 my-1", children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "grid grid-cols-4 gap-1 items-center justify-items-center", children: Array.from({ length: 12 }).map((_, cellIdx) => {
        const r = Math.floor(cellIdx / 4);
        const c = cellIdx % 4;
        const slot = netLayout.find((n) => n.row === r && n.col === c);
        if (!slot) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "w-11 h-11" }, cellIdx);
        return renderFace(slot.face);
      }) }) }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "grid grid-cols-4 gap-1 pt-1 border-t border-slate-800 text-[10px] font-mono shrink-0", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#080D16] px-1.5 py-0.5 rounded flex justify-between", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-500", children: "\u672A\u77E5" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-200", children: stats.unknownCount })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#080D16] px-1.5 py-0.5 rounded flex justify-between", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-500", children: "\u51B2\u7A81" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: stats.conflictCount > 0 ? "text-[#FFBF69]" : "text-slate-200", children: stats.conflictCount })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#080D16] px-1.5 py-0.5 rounded flex justify-between", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-500", children: "\u504F\u5DEE" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: stats.mismatchCount > 0 ? "text-[#FF667B]" : "text-slate-200", children: stats.mismatchCount })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#080D16] px-1.5 py-0.5 rounded flex justify-between", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-500", children: "\u6821\u9A8C" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: validationStatus === "VALID_SOLVABLE" ? "text-[#30D6A0]" : "text-slate-300", children: validationStatus === "VALID_SOLVABLE" ? "\u901A\u8FC7" : validationStatus === "INCOMPLETE" ? "\u672A\u5168" : "\u5F85\u68C0" })
        ] })
      ] })
    ] });
  };
  var CompactTelemetryCard = ({ telemetry: t }) => {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#101827] border border-slate-800/90 rounded-lg p-2.5 flex flex-col justify-between h-full min-h-0", children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-1.5 mb-1.5 shrink-0", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1.5", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Activity, { className: "w-3.5 h-3.5 text-[#3DE8E5]" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[11px] font-semibold tracking-wider text-slate-200 uppercase", children: "ROBOT TELEMETRY \xB7 \u9065\u6D4B\u76D1\u63A7" })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[10px] font-mono text-slate-500", children: "mjData" })
      ] }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex-1 grid grid-cols-2 gap-1.5 text-[11px] min-h-0", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#080D16] border border-slate-800/80 rounded px-2 py-1 flex flex-col justify-center", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[10px] text-slate-400", children: "\u63A5\u89E6\u529B" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "font-mono font-semibold text-slate-100", children: t.contactForceN !== null ? `${t.contactForceN.toFixed(2)} N` : "--" })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#080D16] border border-slate-800/80 rounded px-2 py-1 flex flex-col justify-center", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[10px] text-slate-400", children: "\u5939\u722A\u72B6\u6001" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "font-mono font-semibold text-slate-100 truncate", children: [
            t.gripperWidthMm !== null ? `${t.gripperWidthMm.toFixed(1)} mm` : "--",
            " ",
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "text-[9px] text-[#30D6A0]", children: [
              "(",
              t.gripperState,
              ")"
            ] })
          ] })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#080D16] border border-slate-800/80 rounded px-2 py-1 flex flex-col justify-center", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[10px] text-slate-400", children: "\u5B9E\u9645\u5C42\u8F6C\u89D2" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "font-mono font-semibold text-[#3DE8E5]", children: t.layerTurnAngleDeg !== null ? `${t.targetLayer || "U"}: ${t.layerTurnAngleDeg.toFixed(1)}\xB0` : "--" })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#080D16] border border-slate-800/80 rounded px-2 py-1 flex flex-col justify-center", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[10px] text-slate-400", children: "\u78B0\u649E\u4E0E\u6ED1\u79FB" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "font-mono font-semibold", children: t.collisionDetected === null ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-400", children: "--" }) : t.collisionDetected || t.slipDetected ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[#FF667B]", children: "\u5F02\u5E38\u544A\u8B66" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[#30D6A0]", children: "\u6B63\u5E38 (\u65E0\u6ED1\u79FB)" }) })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "col-span-2 bg-[#080D16] border border-slate-800/80 rounded px-2 py-1 flex items-center justify-between gap-2", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[10px] text-slate-400 shrink-0", children: "\u7269\u4F53\u5750\u6807 & \u5173\u8282" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "font-mono text-[10px] text-slate-200 truncate", children: t.cubePositionMm ? `XYZ[${t.cubePositionMm.map((v) => v.toFixed(1)).join(",")}] \xB7 u:${t.jointPositionsRad?.u_layer ?? "--"}rad` : "--" })
        ] })
      ] })
    ] });
  };
  var CapabilityAndSettingsView = ({ wsUrl, onWsUrlChange, seedInput, onSeedChange, capabilities, commandLog }) => {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("main", { className: "flex-1 overflow-y-auto p-4 max-w-5xl mx-auto w-full space-y-3.5 text-xs", children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "grid grid-cols-1 lg:grid-cols-2 gap-3.5", children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#101827] border border-slate-800 rounded-lg p-4 space-y-3", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-2 border-b border-slate-800 pb-2", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Settings, { className: "w-4 h-4 text-[#3DE8E5]" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", { className: "font-semibold text-slate-100", children: "\u7CFB\u7EDF\u8BBE\u7F6E\u4E0E\u540E\u7AEF SimulationSession \u7AEF\u70B9" })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("label", { className: "block text-slate-400 mb-1", children: "WebSocket \u5730\u5740" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            "input",
            {
              type: "text",
              value: wsUrl,
              onChange: (e) => onWsUrlChange(e.target.value),
              className: "w-full px-3 py-1.5 rounded bg-[#080D16] border border-slate-700 font-mono text-slate-200"
            }
          )
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("label", { className: "block text-slate-400 mb-1", children: "\u9ED8\u8BA4\u5B9E\u9A8C\u968F\u673A\u79CD\u5B50 (Seed)" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            "input",
            {
              type: "number",
              value: seedInput,
              onChange: (e) => onSeedChange(Number(e.target.value) || 0),
              className: "w-32 px-3 py-1.5 rounded bg-[#080D16] border border-slate-700 font-mono text-slate-200"
            }
          )
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-slate-400 mb-1", children: "\u63A7\u5236\u53F0\u64CD\u4F5C\u5BA1\u8BA1\u65E5\u5FD7" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "h-44 overflow-y-auto p-2.5 rounded bg-[#080D16] border border-slate-800 font-mono text-[11px] text-slate-300 space-y-1", children: commandLog.map((line, i) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { children: line }, i)) })
        ] })
      ] }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#101827] border border-slate-800 rounded-lg p-4 space-y-2.5", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between border-b border-slate-800 pb-2", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-2", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ShieldCheck, { className: "w-4 h-4 text-[#30D6A0]" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", { className: "font-semibold text-slate-100", children: "Skill Registry \u7269\u7406\u80FD\u529B\u8FB9\u754C" })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(FileCode2, { className: "w-4 h-4 text-[#548CFF]" })
        ] }),
        capabilities ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "p-2 rounded bg-[#080D16] border border-slate-800 text-[11px] text-slate-300", children: capabilities.physical_limitations_summary }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "space-y-1.5 max-h-60 overflow-y-auto", children: capabilities.skills.map((sk) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2 rounded bg-[#080D16] border border-slate-800 space-y-0.5", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "font-mono text-[#3DE8E5]", children: sk.skill_id }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                "span",
                {
                  className: `px-1.5 py-0.2 rounded text-[10px] font-mono ${sk.implemented ? "bg-[#30D6A0]/15 text-[#30D6A0]" : "bg-[#FFBF69]/15 text-[#FFBF69]"}`,
                  children: sk.implemented ? "IMPLEMENTED" : "UNIMPLEMENTED"
                }
              )
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10.5px] text-slate-400", children: sk.description })
          ] }, sk.skill_id)) })
        ] }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-slate-500", children: "\u8FDE\u63A5 LIVE \u540E\u7AEF\u540E\u663E\u793A\u52A8\u6001\u6CE8\u518C\u7684 SkillRegistry\u3002" })
      ] })
    ] }) });
  };
  var DIM_LABELS = {
    L1_SKILL_SELECTION: "L1 Skill Selection",
    L2_STATE_AWARE_PLANNING: "L2 State-Aware Planning",
    L3_PERCEPTION_GROUNDED_REASONING: "L3 Perception-Grounded",
    L4_FAILURE_RECOVERY: "L4 Failure Recovery",
    L5_GENERALIZATION: "L5 Generalization"
  };
  var SOURCE_BADGE_STYLES = {
    REAL_ONLINE_MODEL: "bg-[#30D6A0]/15 text-[#30D6A0] border-[#30D6A0]/40",
    REAL_MUJOCO: "bg-[#548CFF]/15 text-[#548CFF] border-[#548CFF]/40",
    OFFLINE_REPLAY: "bg-[#3DE8E5]/15 text-[#3DE8E5] border-[#3DE8E5]/40",
    COUNTERFACTUAL_TEST: "bg-[#FFBF69]/15 text-[#FFBF69] border-[#FFBF69]/40",
    DETERMINISTIC_RULE: "bg-slate-700/60 text-slate-200 border-slate-600",
    FAKE_PROVIDER: "bg-[#F05D5E]/20 text-[#F05D5E] border-[#F05D5E]/50"
  };
  function getVerdictBadgeCls(verdict) {
    if (verdict === "PASS") return "px-1.5 py-0.2 rounded shrink-0 bg-[#30D6A0]/20 text-[#30D6A0]";
    if (verdict === "FAIL") return "px-1.5 py-0.2 rounded shrink-0 bg-[#F05D5E]/20 text-[#F05D5E]";
    return "px-1.5 py-0.2 rounded shrink-0 bg-slate-800 text-slate-300";
  }
  var TaskAgentBenchmarkView = ({ httpBase }) => {
    const [loading, setLoading] = (0, import_react3.useState)(false);
    const [errorMsg, setErrorMsg] = (0, import_react3.useState)(null);
    const [apiStatus, setApiStatus] = (0, import_react3.useState)("NOT_RUN");
    const [runs, setRuns] = (0, import_react3.useState)([]);
    const [selectedRunId, setSelectedRunId] = (0, import_react3.useState)("");
    const [sourceBadge, setSourceBadge] = (0, import_react3.useState)("");
    const [result, setResult] = (0, import_react3.useState)(null);
    const [activeSubTab, setActiveSubTab] = (0, import_react3.useState)("OVERVIEW");
    const [traceFilterGroup, setTraceFilterGroup] = (0, import_react3.useState)("ALL");
    const [traceFilterVerdict, setTraceFilterVerdict] = (0, import_react3.useState)("ALL");
    const [traceFilterDim, setTraceFilterDim] = (0, import_react3.useState)("ALL");
    const [selectedRecordId, setSelectedRecordId] = (0, import_react3.useState)("");
    const fetchBenchmark = async (runId) => {
      setLoading(true);
      setErrorMsg(null);
      try {
        const qs = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
        const resp = await fetch(`${httpBase}/api/m4d/benchmark/latest${qs}`);
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }
        const data = await resp.json();
        setRuns(Array.isArray(data.available_runs) ? data.available_runs : []);
        if (data.status === "OK" && data.result) {
          setApiStatus("OK");
          setSourceBadge(String(data.source_badge || ""));
          setResult(data.result);
          setSelectedRunId(String(data.result.benchmark_run_id || ""));
          if (Array.isArray(data.result.decision_records) && data.result.decision_records.length > 0) {
            setSelectedRecordId(data.result.decision_records[0].record_id);
          }
        } else {
          setApiStatus("NOT_RUN");
          setResult(null);
        }
      } catch (err) {
        setApiStatus("UNCONNECTED");
        setErrorMsg(err instanceof Error ? err.message : "\u65E0\u6CD5\u52A0\u8F7D Benchmark API");
      } finally {
        setLoading(false);
      }
    };
    (0, import_react3.useEffect)(() => {
      fetchBenchmark();
    }, [httpBase]);
    const fmtPct = (m) => {
      if (!m || m.value === null || m.value === void 0) return "N/A";
      return `${(m.value * 100).toFixed(1)}% (${m.numerator}/${m.denominator})`;
    };
    const filteredRecords = (0, import_react3.useMemo)(() => {
      if (!result) return [];
      const all = [...result.decision_records || [], ...result.guide_ablation_records || []];
      return all.filter((r) => {
        if (traceFilterGroup !== "ALL" && r.planner_group !== traceFilterGroup) return false;
        if (traceFilterDim !== "ALL" && r.capability_dimension !== traceFilterDim) return false;
        if (traceFilterVerdict !== "ALL" && r.oracle_result.verdict !== traceFilterVerdict) return false;
        return true;
      });
    }, [result, traceFilterGroup, traceFilterVerdict, traceFilterDim]);
    const selectedRecord = (0, import_react3.useMemo)(
      () => filteredRecords.find((r) => r.record_id === selectedRecordId) || filteredRecords[0] || null,
      [filteredRecords, selectedRecordId]
    );
    const realCards = Object.values(result?.real_scorecards || {});
    const fakeCards = Object.values(result?.fake_validation_scorecards || {});
    const allCards = [...realCards, ...fakeCards];
    const abConds = result?.vlm_ablation_summary?.by_condition || result?.vlm_ablation_summary?.fake_only?.by_condition || {};
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("main", { className: "flex-1 overflow-y-auto bg-[#080D16] p-4 space-y-4 text-xs", children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#101827] border border-slate-800 rounded-lg p-3 flex flex-wrap items-center justify-between gap-3", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-2.5 flex-wrap", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Bot, { className: "w-4 h-4 text-[#3DE8E5]" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", { className: "font-semibold text-sm text-slate-100", children: "M4-D Task Agent \u80FD\u529B\u57FA\u51C6\u6D4B\u8BD5 (Benchmark)" }),
          result && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: `px-2 py-0.5 rounded border text-[10px] font-mono ${SOURCE_BADGE_STYLES[sourceBadge] || "bg-slate-800 text-slate-200 border-slate-700"}`, children: sourceBadge || result.execution_mode }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-[10px] font-mono text-slate-300", children: [
              "VERSION: ",
              result.benchmark_version
            ] })
          ] })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-2 flex-wrap", children: [
          runs.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            "select",
            {
              value: selectedRunId,
              onChange: (e) => fetchBenchmark(e.target.value),
              className: "px-2.5 py-1 rounded bg-[#080D16] border border-slate-700 text-[11px] font-mono text-slate-200",
              children: runs.map((r) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("option", { value: r.benchmark_run_id, children: [
                r.benchmark_run_id,
                " (",
                r.execution_mode,
                " | D=",
                r.decision_count,
                ")"
              ] }, r.benchmark_run_id))
            }
          ),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
            "button",
            {
              onClick: () => fetchBenchmark(selectedRunId || void 0),
              disabled: loading,
              className: "px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 flex items-center gap-1",
              children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RefreshCw, { className: `w-3.5 h-3.5 ${loading ? "animate-spin" : ""}` }),
                " \u5237\u65B0"
              ]
            }
          ),
          result && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
            "a",
            {
              href: `${httpBase}/api/m4d/benchmark/export?run_id=${encodeURIComponent(result.benchmark_run_id)}`,
              className: "px-2.5 py-1 rounded bg-[#548CFF]/20 hover:bg-[#548CFF]/30 border border-[#548CFF]/40 text-[#548CFF] flex items-center gap-1",
              children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Download, { className: "w-3.5 h-3.5" }),
                " \u5BFC\u51FA Benchmark ZIP"
              ]
            }
          )
        ] })
      ] }),
      result?.contains_fake_provider && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2.5 rounded bg-[#F05D5E]/15 border border-[#F05D5E]/40 text-[#F05D5E] flex items-center gap-2", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(TriangleAlert, { className: "w-4 h-4 shrink-0" }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
          "\u5F53\u524D Run \u5305\u542B ",
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("code", { className: "font-mono font-semibold", children: "FAKE_PROVIDER" }),
          " \u9A8C\u8BC1\u6570\u636E\uFF1AFake Provider \u4EC5\u7528\u4E8E\u9A8C\u8BC1\u6D4B\u8BD5\u7BA1\u7EBF\uFF0C\u5DF2\u4E25\u683C\u9694\u79BB\u5230",
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("code", { className: "font-mono", children: " fake_validation_scorecards" }),
          "\uFF0C",
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("strong", { children: "\u7EDD\u4E0D\u8BA1\u5165\u771F\u5B9E LLM Agent \u80FD\u529B\u8BC4\u5206" }),
          "\u3002"
        ] })
      ] }),
      apiStatus === "NOT_RUN" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#101827] border border-slate-800 rounded-lg p-6 text-center space-y-2", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-sm font-semibold text-slate-200", children: "\u5C1A\u672A\u68C0\u6D4B\u5230\u5DF2\u4FDD\u5B58\u7684 M4-D Benchmark \u7ED3\u679C (NOT_RUN)" }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-slate-400", children: [
          "\u8BF7\u8FD0\u884C ",
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("code", { className: "font-mono text-[#3DE8E5]", children: "python scripts/run_m4d_benchmark.py --mode online_real --run-vlm-ablation --run-guide-ablation --closed-loop" }),
          " \u540E\u70B9\u51FB\u5237\u65B0\u3002"
        ] })
      ] }),
      apiStatus === "UNCONNECTED" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#101827] border border-[#F05D5E]/40 rounded-lg p-4 text-[#F05D5E]", children: [
        "\u65E0\u6CD5\u8BFB\u53D6 Benchmark \u63A5\u53E3 (",
        httpBase,
        "/api/m4d/benchmark/latest): ",
        errorMsg
      ] }),
      result && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "flex items-center gap-1 border-b border-slate-800 pb-2", children: [
          { id: "OVERVIEW", label: "\u4E94\u7EF4\u80FD\u529B\u699C\u5355 & \u5BF9\u7167\u7EC4" },
          { id: "ABLATIONS", label: "VLM \u56E0\u679C\u6D88\u878D & Guide \u6D88\u878D" },
          { id: "CLOSED_LOOP", label: `MuJoCo \u95ED\u73AF\u8BC4\u4F30 (${result.closed_loop_episodes.length})` },
          { id: "TRACES", label: `\u9519\u8BEF\u6848\u4F8B\u4E0E Decision Trace (${result.decision_records.length})` }
        ].map((t) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
          "button",
          {
            onClick: () => setActiveSubTab(t.id),
            className: `px-3 py-1 rounded text-[11px] font-medium transition-colors ${activeSubTab === t.id ? "bg-[#3DE8E5]/15 text-[#3DE8E5] border border-[#3DE8E5]/40" : "text-slate-400 hover:text-slate-200 bg-[#101827] border border-slate-800"}`,
            children: t.label
          },
          t.id
        )) }),
        activeSubTab === "OVERVIEW" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-4", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#101827] border border-slate-800 rounded-lg p-3 overflow-x-auto", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { className: "font-semibold text-slate-200 mb-2", children: "\u5BF9\u7167\u7EC4\u80FD\u529B\u6307\u6807\uFF08L1-L5 \u72EC\u7ACB\u8BC4\u5206\uFF0C\u4E25\u7981\u5408\u5E76\u4E3A\u5355\u4E00\u5206\u6570\uFF09" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", { className: "w-full text-left border-collapse font-mono text-[11px]", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { className: "border-b border-slate-800 text-slate-400", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Planner Group / Guide" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "\u6570\u636E\u6765\u6E90" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Legal" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Schema" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Appropriate" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Forbidden" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Evidence" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Mean(ms)" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5", children: "Tokens" })
              ] }) }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: allCards.map((sc) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { className: "border-b border-slate-800/60 hover:bg-slate-800/30", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", { className: "py-1.5 pr-3 text-slate-100", children: [
                  sc.group_label,
                  !sc.included_in_real_agent_ranking && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "ml-1.5 px-1 py-0.2 rounded bg-[#F05D5E]/20 text-[#F05D5E] text-[9px]", children: "EXCLUDED_FAKE" })
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3", children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: `px-1.5 py-0.5 rounded border text-[9.5px] ${SOURCE_BADGE_STYLES[sc.execution_source_label] || ""}`, children: sc.execution_source_label }) }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3", children: fmtPct(sc.decision_metrics.legal_action_rate) }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3", children: fmtPct(sc.decision_metrics.schema_validity_rate) }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3 font-semibold text-[#3DE8E5]", children: fmtPct(sc.decision_metrics.decision_appropriateness_rate) }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3 text-[#F05D5E]", children: fmtPct(sc.decision_metrics.forbidden_action_rate) }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3", children: fmtPct(sc.decision_metrics.evidence_grounding_rate) }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3", children: sc.latency_summary_ms?.mean_ms ?? "N/A" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5", children: sc.token_summary?.total_tokens ?? 0 })
              ] }, sc.group_label)) })
            ] })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "grid grid-cols-1 lg:grid-cols-2 gap-4", children: allCards.map((sc) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#101827] border border-slate-800 rounded-lg p-3 space-y-2.5", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between border-b border-slate-800 pb-1.5", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "font-mono font-semibold text-slate-100", children: sc.group_label }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: `px-1.5 py-0.5 rounded border text-[9.5px] font-mono ${SOURCE_BADGE_STYLES[sc.execution_source_label] || ""}`, children: sc.execution_source_label })
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "space-y-1.5", children: Object.entries(sc.per_dimension || {}).map(([dim, ds]) => {
              const pct = ds.pass_rate.value !== null ? Math.round(ds.pass_rate.value * 100) : 0;
              return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-0.5", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex justify-between text-[10.5px] font-mono", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-300", children: DIM_LABELS[dim] || dim }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "text-slate-200", children: [
                    ds.pass_rate.value !== null ? `${pct}% (${ds.passed_count}/${ds.pass_rate.denominator})` : "N/A",
                    ds.incomparable_count > 0 ? ` [INCOMP:${ds.incomparable_count}]` : ""
                  ] })
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "h-1.5 bg-slate-800 rounded overflow-hidden", children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                  "div",
                  {
                    className: `h-full ${sc.is_fake_provider ? "bg-[#F05D5E]" : "bg-[#3DE8E5]"}`,
                    style: { width: `${pct}%` }
                  }
                ) })
              ] }, dim);
            }) }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "pt-1 border-t border-slate-800/70 flex flex-wrap gap-1.5 text-[10px] font-mono", children: Object.entries(sc.failure_attribution_counts || {}).map(([cat, cnt]) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "px-1.5 py-0.5 rounded bg-[#080D16] border border-slate-800 text-slate-300", children: [
              cat,
              ": ",
              cnt
            ] }, cat)) })
          ] }, sc.group_label)) })
        ] }),
        activeSubTab === "ABLATIONS" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-4", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#101827] border border-slate-800 rounded-lg p-3 space-y-2", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { className: "font-semibold text-slate-200", children: "L3 VLM \u8BED\u4E49\u56E0\u679C\u6D88\u878D (VLM_TRUE vs ABSENT / SWAPPED / CONTRADICTORY / LOW_CONFIDENCE)" }),
            Object.keys(abConds).length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-slate-500", children: "\u5F53\u524D Run \u672A\u5305\u542B L3 VLM \u6D88\u878D\u8BB0\u5F55\u3002" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", { className: "w-full text-left border-collapse font-mono text-[11px]", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { className: "border-b border-slate-800 text-slate-400", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Condition" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "N (Comparable)" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Pass" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Accuracy" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Forbidden Rate" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5", children: "Evidence Grounding" })
              ] }) }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: Object.entries(abConds).map(([cond, st]) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { className: "border-b border-slate-800/60", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3 text-[#3DE8E5]", children: cond }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", { className: "py-1.5 pr-3", children: [
                  st.comparable_n,
                  " / ",
                  st.n
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3", children: st.passed }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3", children: fmtPct(st.accuracy) }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3 text-[#F05D5E]", children: fmtPct(st.forbidden_rate) }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5", children: fmtPct(st.evidence_grounding_rate) })
              ] }, cond)) })
            ] })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#101827] border border-slate-800 rounded-lg p-3 space-y-2", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { className: "font-semibold text-slate-200", children: "Prompt Guide \u6D88\u878D (GUIDE_FULL vs GUIDE_MINIMAL)" }),
            !result.guide_ablation_summary || Object.keys(result.guide_ablation_summary).length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-slate-500", children: "\u5F53\u524D Run \u672A\u5305\u542B Prompt Guide \u6D88\u878D\u5BF9\u7167\u3002" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", { className: "w-full text-left border-collapse font-mono text-[11px]", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { className: "border-b border-slate-800 text-slate-400", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Planner Group" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "GUIDE_FULL Acc (N)" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "GUIDE_MINIMAL Acc (N)" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5", children: "Delta (MIN - FULL)" })
              ] }) }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: Object.entries(result.guide_ablation_summary).map(([grp, st]) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { className: "border-b border-slate-800/60", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3 text-slate-100", children: grp }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", { className: "py-1.5 pr-3", children: [
                  (st.guide_full_acc * 100).toFixed(1),
                  "% (",
                  st.guide_full_n,
                  ")"
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", { className: "py-1.5 pr-3", children: [
                  (st.guide_minimal_acc * 100).toFixed(1),
                  "% (",
                  st.guide_minimal_n,
                  ")"
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", { className: "py-1.5 text-[#3DE8E5]", children: [
                  st.delta_minimal_minus_full * 100 >= 0 ? "+" : "",
                  (st.delta_minimal_minus_full * 100).toFixed(1),
                  "%"
                ] })
              ] }, grp)) })
            ] })
          ] })
        ] }),
        activeSubTab === "CLOSED_LOOP" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#101827] border border-slate-800 rounded-lg p-3 space-y-2 overflow-x-auto", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { className: "font-semibold text-slate-200", children: "Layer B \u771F\u5B9E MuJoCo \u95ED\u73AF\u8BC4\u4F30 Episodes (\u533A\u5206 Agent \u51B3\u7B56\u4E0E\u7269\u7406 Skill \u6210\u8D25)" }),
          result.closed_loop_episodes.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-slate-500", children: "\u5F53\u524D Run \u672A\u5305\u542B Closed-Loop MuJoCo Episodes\u3002" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", { className: "w-full text-left border-collapse font-mono text-[11px]", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { className: "border-b border-slate-800 text-slate-400", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Scenario" }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Group" }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Sources" }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Status" }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Goal" }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Attribution" }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5 pr-3", children: "Skills Executed" }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { className: "py-1.5", children: "Wall(s)" })
            ] }) }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: result.closed_loop_episodes.map((ep) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { className: "border-b border-slate-800/60", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3 text-slate-100", children: ep.scenario_id }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3", children: ep.planner_group }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3", children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "flex gap-1 flex-wrap", children: ep.execution_source_labels.map((lb) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: `px-1 py-0.2 rounded border text-[9px] ${SOURCE_BADGE_STYLES[lb] || ""}`, children: lb }, lb)) }) }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3", children: ep.mission_status }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: `py-1.5 pr-3 ${ep.goal_achieved ? "text-[#30D6A0]" : "text-[#F05D5E]"}`, children: String(ep.goal_achieved) }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3", children: ep.failure_attribution.primary_category }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5 pr-3 text-slate-300", children: ep.skills_executed.join(" -> ") }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { className: "py-1.5", children: ep.wall_time_s.toFixed(2) })
            ] }, ep.episode_id)) })
          ] })
        ] }),
        activeSubTab === "TRACES" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "grid grid-cols-1 lg:grid-cols-12 gap-3", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "lg:col-span-7 bg-[#101827] border border-slate-800 rounded-lg p-3 space-y-2", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex flex-wrap gap-2 items-center justify-between", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("h3", { className: "font-semibold text-slate-200", children: [
                "\u51B3\u7B56\u8BB0\u5F55\u4E0E\u5931\u8D25\u6848\u4F8B\u8FC7\u6EE4 (",
                filteredRecords.length,
                ")"
              ] }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex flex-wrap gap-1.5 font-mono text-[10.5px]", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", { value: traceFilterGroup, onChange: (e) => setTraceFilterGroup(e.target.value), className: "px-2 py-0.5 rounded bg-[#080D16] border border-slate-700 text-slate-200", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "ALL", children: "All Groups" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "DETERMINISTIC_BASELINE", children: "DETERMINISTIC" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "LLM_AGENT_CV_ONLY", children: "LLM_CV_ONLY" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "LLM_AGENT_CV_VLM", children: "LLM_CV_VLM" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "SINGLE_MODEL_BASELINE", children: "SINGLE_MODEL" })
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", { value: traceFilterDim, onChange: (e) => setTraceFilterDim(e.target.value), className: "px-2 py-0.5 rounded bg-[#080D16] border border-slate-700 text-slate-200", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "ALL", children: "All Dimensions" }),
                  Object.keys(DIM_LABELS).map((d) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: d, children: d }, d))
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", { value: traceFilterVerdict, onChange: (e) => setTraceFilterVerdict(e.target.value), className: "px-2 py-0.5 rounded bg-[#080D16] border border-slate-700 text-slate-200", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "ALL", children: "All Verdicts" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "FAIL", children: "FAIL Only" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "PASS", children: "PASS Only" }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "INCOMPARABLE", children: "INCOMPARABLE" })
                ] })
              ] })
            ] }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "max-h-96 overflow-y-auto space-y-1 font-mono text-[10.5px]", children: filteredRecords.map((r) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
              "button",
              {
                onClick: () => setSelectedRecordId(r.record_id),
                className: `w-full text-left p-2 rounded border flex items-center justify-between gap-2 ${selectedRecord?.record_id === r.record_id ? "bg-[#3DE8E5]/10 border-[#3DE8E5]/50" : "bg-[#080D16] border-slate-800 hover:border-slate-700"}`,
                children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "truncate", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-100", children: r.benchmark_case_id }),
                    " ",
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "text-slate-400", children: [
                      "[",
                      r.planner_group,
                      " / ",
                      r.guide_mode,
                      "]"
                    ] }),
                    " ",
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "text-[#3DE8E5]", children: [
                      "-> ",
                      r.normalized_action
                    ] })
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: getVerdictBadgeCls(r.oracle_result.verdict), children: r.oracle_result.verdict })
                ]
              },
              r.record_id
            )) })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "lg:col-span-5 bg-[#101827] border border-slate-800 rounded-lg p-3 space-y-2 font-mono text-[10.5px]", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { className: "font-sans font-semibold text-xs text-slate-200", children: "Decision Trace \u8BE6\u60C5" }),
            selectedRecord ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-2", children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "flex flex-wrap gap-1", children: selectedRecord.execution_source_labels.map((lb) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: `px-1.5 py-0.5 rounded border text-[9.5px] ${SOURCE_BADGE_STYLES[lb] || ""}`, children: lb }, lb)) }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2 rounded bg-[#080D16] border border-slate-800 space-y-1 text-slate-300", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
                  "Case: ",
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-100", children: selectedRecord.benchmark_case_id }),
                  " (",
                  selectedRecord.source_type,
                  ")"
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
                  "Action: ",
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[#3DE8E5]", children: selectedRecord.normalized_action }),
                  " params=",
                  JSON.stringify(selectedRecord.parameters)
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
                  "Model: ",
                  selectedRecord.model_name,
                  " | Latency: ",
                  selectedRecord.latency_ms,
                  "ms | Call: ",
                  selectedRecord.model_call_status
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
                  "Evidence Refs: ",
                  JSON.stringify(selectedRecord.evidence_references)
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
                  "Safety Gate: ",
                  selectedRecord.safety_validation.safety_gate_status,
                  " (",
                  selectedRecord.safety_validation.reason,
                  ")"
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
                  "Oracle Verdict: ",
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: selectedRecord.oracle_result.verdict === "PASS" ? "text-[#30D6A0]" : "text-[#F05D5E]", children: selectedRecord.oracle_result.verdict }),
                  " | Attribution: ",
                  selectedRecord.failure_attribution.primary_category
                ] })
              ] }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "p-2 rounded bg-[#080D16] border border-slate-800 text-slate-300 font-sans", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-slate-400 text-[10px] mb-0.5", children: "Reason Summary & Oracle Notes" }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { children: selectedRecord.reason_summary || "\u2014" }),
                selectedRecord.oracle_result.notes.length > 0 && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "mt-1 text-[#FFBF69] font-mono text-[10px]", children: selectedRecord.oracle_result.notes.join("; ") })
              ] }),
              selectedRecord.prompt_sha256 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "text-[10px] text-slate-500 truncate", children: [
                "prompt_sha256: ",
                selectedRecord.prompt_sha256
              ] })
            ] }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-slate-500", children: "\u9009\u62E9\u4E00\u6761\u8BB0\u5F55\u67E5\u770B\u8BE6\u7EC6 Trace\u3002" })
          ] })
        ] })
      ] })
    ] });
  };
  function getDefaultWsUrl() {
    if (typeof window !== "undefined" && window.location.protocol.startsWith("http")) {
      const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const base = window.location.pathname === "/cube-relay" || window.location.pathname.startsWith("/cube-relay/") ? "/cube-relay" : "";
      return `${wsProto}//${window.location.host}${base}/ws/session`;
    }
    return "ws://127.0.0.1:8765/ws/session";
  }
  function getDefaultRuntimeMode() {
    if (typeof window !== "undefined" && window.location.protocol.startsWith("http")) {
      return "LIVE";
    }
    return "SAMPLE";
  }
  function App() {
    const [activeNav, setActiveNav] = (0, import_react3.useState)("CONSOLE");
    const [mode, setMode] = (0, import_react3.useState)(() => getDefaultRuntimeMode());
    const [wsUrl, setWsUrl] = (0, import_react3.useState)(() => getDefaultWsUrl());
    const [wsConnected, setWsConnected] = (0, import_react3.useState)(false);
    const [seedInput, setSeedInput] = (0, import_react3.useState)(0);
    const [selectedMission, setSelectedMission] = (0, import_react3.useState)("RELAY_SOLVE_CUBE");
    const [selectedScrambleSteps, setSelectedScrambleSteps] = (0, import_react3.useState)(5);
    const [techDrawerOpen, setTechDrawerOpen] = (0, import_react3.useState)(false);
    const [snapshot, setSnapshot] = (0, import_react3.useState)(
      () => getDefaultRuntimeMode() === "LIVE" ? createDisconnectedLiveSnapshot(0, "RELAY_SOLVE_CUBE") : createSampleSnapshot("RELAY_SOLVE_CUBE", SAMPLE_TIMELINE[3])
    );
    const [selectedEventId, setSelectedEventId] = (0, import_react3.useState)("ev-4");
    const [commandLog, setCommandLog] = (0, import_react3.useState)(["[INIT] CubeRelay M3-D \u63A7\u5236\u53F0\u5DF2\u521D\u59CB\u5316"]);
    const [debugOverlays, setDebugOverlays] = (0, import_react3.useState)({
      contactForces: true,
      collisionGeoms: false,
      tcpFrame: true,
      hudVisible: true
    });
    const [previewScreenshotUrl, setPreviewScreenshotUrl] = (0, import_react3.useState)(null);
    const replayVideoRef = (0, import_react3.useRef)(null);
    const [replayVideoUrl, setReplayVideoUrl] = (0, import_react3.useState)(null);
    const [replayTiming, setReplayTiming] = (0, import_react3.useState)(null);
    const wsRef = (0, import_react3.useRef)(null);
    const [startModalOpen, setStartModalOpen] = (0, import_react3.useState)(false);
    const [startModalPassword, setStartModalPassword] = (0, import_react3.useState)("");
    const [startModalError, setStartModalError] = (0, import_react3.useState)(null);
    const [startModalSubmitting, setStartModalSubmitting] = (0, import_react3.useState)(false);
    const [exportModalOpen, setExportModalOpen] = (0, import_react3.useState)(false);
    const [exportScope, setExportScope] = (0, import_react3.useState)("full_mission");
    const [exportIncludeRgbd, setExportIncludeRgbd] = (0, import_react3.useState)(true);
    const [exportIncludeHighFreq, setExportIncludeHighFreq] = (0, import_react3.useState)(true);
    const [exportIncludeAuditTruth, setExportIncludeAuditTruth] = (0, import_react3.useState)(false);
    const [exportSelectedRunId, setExportSelectedRunId] = (0, import_react3.useState)("");
    const [exportRuns, setExportRuns] = (0, import_react3.useState)([]);
    const [exportSubmitting, setExportSubmitting] = (0, import_react3.useState)(false);
    const [exportStatusMsg, setExportStatusMsg] = (0, import_react3.useState)(null);
    const [exportErrorMsg, setExportErrorMsg] = (0, import_react3.useState)(null);
    const startPasswordInputRef = (0, import_react3.useRef)(null);
    const appendLog = (msg) => {
      const ts = (/* @__PURE__ */ new Date()).toTimeString().slice(0, 8);
      setCommandLog((prev) => [`[${ts}] ${msg}`, ...prev.slice(0, 29)]);
    };
    (0, import_react3.useEffect)(() => {
      if (!startModalOpen) return;
      const focusTimer = window.setTimeout(() => {
        startPasswordInputRef.current?.focus();
      }, 0);
      const onKeyDown = (event) => {
        if (event.key === "Escape" && !startModalSubmitting) {
          setStartModalPassword("");
          setStartModalError(null);
          setStartModalOpen(false);
        }
      };
      window.addEventListener("keydown", onKeyDown);
      return () => {
        window.clearTimeout(focusTimer);
        window.removeEventListener("keydown", onKeyDown);
      };
    }, [startModalOpen, startModalSubmitting]);
    (0, import_react3.useEffect)(() => {
      if (mode !== "SAMPLE") return;
      const url = generateOffscreenMujocoFrameUrl(
        snapshot.active_camera,
        snapshot.telemetry.layerTurnAngleDeg ?? 0,
        debugOverlays
      );
      if (url) {
        setSnapshot((prev) => ({ ...prev, main_frame_url: url, frame_source: "SYNTHETIC_SAMPLE" }));
      }
    }, [
      mode,
      snapshot.active_camera,
      snapshot.telemetry.layerTurnAngleDeg,
      debugOverlays.contactForces,
      debugOverlays.collisionGeoms,
      debugOverlays.tcpFrame
    ]);
    const handleSwitchMode = (nextMode) => {
      setMode(nextMode);
      setStartModalPassword("");
      setStartModalError(null);
      if (nextMode === "SAMPLE") {
        const targetEv = SAMPLE_TIMELINE.find((e) => e.event_id === selectedEventId) || SAMPLE_TIMELINE[3];
        setSnapshot(createSampleSnapshot(selectedMission, targetEv));
        appendLog(`\u5DF2\u5207\u6362\u81F3 SAMPLE \u6A21\u5F0F\uFF08SYNTHETIC SAMPLE \xB7 ${selectedMission}\uFF09`);
      } else if (nextMode === "LIVE") {
        setSnapshot(createDisconnectedLiveSnapshot(seedInput, selectedMission));
        appendLog(`\u5DF2\u5207\u6362\u81F3 LIVE \u5B9E\u65F6\u4EFF\u771F\u6A21\u5F0F\uFF0C\u6B63\u5728\u8FDE\u63A5 ${wsUrl}...`);
      } else if (nextMode === "REPLAY") {
        if (!replayVideoUrl && !previewScreenshotUrl) {
          setSnapshot(createDisconnectedLiveSnapshot(seedInput, selectedMission));
        }
        appendLog("\u5DF2\u5207\u6362\u81F3 PREVIEW / REPLAY \u79BB\u7EBF\u9884\u89C8\u6A21\u5F0F");
      }
    };
    (0, import_react3.useEffect)(() => {
      if (mode !== "LIVE") {
        if (wsRef.current) {
          wsRef.current.close();
          wsRef.current = null;
        }
        setWsConnected(false);
        return;
      }
      let cancelled = false;
      let reconnectTimer = null;
      const connect = () => {
        if (cancelled) return;
        try {
          const ws = new WebSocket(wsUrl);
          wsRef.current = ws;
          ws.onopen = () => {
            if (cancelled) return;
            setWsConnected(true);
            appendLog(`\u5DF2\u8FDE\u63A5 MuJoCo SimulationSession (${wsUrl})`);
            ws.send(JSON.stringify({ type: "GET_STATE" }));
          };
          ws.onmessage = (event) => {
            if (cancelled) return;
            try {
              const data = JSON.parse(event.data);
              if (data.type === "STATE_UPDATE" && data.payload) {
                const next = data.payload;
                if (next.frame_source === "SYNTHETIC_SAMPLE") {
                  return;
                }
                setSnapshot(next);
                if (next.selected_mission_type) {
                  setSelectedMission(next.selected_mission_type);
                }
              } else if (data.type === "COMMAND_RESULT" && data.ok === false) {
                appendLog(`\u540E\u7AEF\u62D2\u7EDD\u6307\u4EE4: ${data.error || "UNKNOWN_ERROR"}`);
              }
            } catch {
            }
          };
          ws.onclose = () => {
            if (cancelled) return;
            setWsConnected(false);
            reconnectTimer = window.setTimeout(connect, 2500);
          };
          ws.onerror = () => ws.close();
        } catch {
          setWsConnected(false);
        }
      };
      connect();
      return () => {
        cancelled = true;
        if (reconnectTimer) window.clearTimeout(reconnectTimer);
        if (wsRef.current) {
          wsRef.current.close();
          wsRef.current = null;
        }
      };
    }, [mode, wsUrl]);
    const getHttpBase = () => wsUrl.replace(/^wss:/, "https:").replace(/^ws:/, "http:").replace(/\/ws\/session$/, "");
    const postBackendCommand = async (cmd) => {
      try {
        const resp = await fetch(`${getHttpBase()}/api/m3d/command`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(cmd)
        });
        const body = await resp.json().catch(() => null);
        if (!resp.ok) {
          return {
            ok: false,
            status: resp.status,
            body,
            detail: typeof body?.detail === "string" ? body.detail : `HTTP ${resp.status}`
          };
        }
        if (body) {
          if (body.snapshot && body.snapshot.frame_source !== "SYNTHETIC_SAMPLE") {
            setSnapshot(body.snapshot);
            setWsConnected(true);
          }
        }
        return { ok: true, status: resp.status, body };
      } catch {
        return { ok: false, status: 0, body: null, detail: "NETWORK_ERROR" };
      }
    };
    const sendBackendCommand = async (cmd, label) => {
      if (mode !== "LIVE") {
        appendLog(`\u5F53\u524D\u4E3A ${mode} \u53EA\u8BFB\u6A21\u5F0F\uFF0C\u6307\u4EE4 [${label}] \u4EC5\u5728 LIVE \u8FDE\u63A5\u540E\u7AEF\u65F6\u6267\u884C`);
        return;
      }
      if (wsConnected && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify(cmd));
        appendLog(`\u5DF2\u901A\u8FC7 WebSocket \u4E0B\u53D1\u6307\u4EE4: ${label}`);
        return;
      }
      const res = await postBackendCommand(cmd);
      if (res.ok) {
        appendLog(`\u5DF2\u901A\u8FC7 HTTP \u4E0B\u53D1\u6307\u4EE4: ${label}`);
        return;
      }
      if (res.status > 0) {
        appendLog(`\u540E\u7AEF\u62D2\u7EDD\u6307\u4EE4 [${label}]: ${res.detail || `HTTP ${res.status}`}`);
        return;
      }
      appendLog(`\u6307\u4EE4\u672A\u53D1\u9001 [${label}]: MuJoCo \u540E\u7AEF\u672A\u8FDE\u63A5`);
    };
    const handleSelectMission = (missionType) => {
      setSelectedMission(missionType);
      if (mode === "SAMPLE") {
        const targetEv = SAMPLE_TIMELINE.find((e) => e.event_id === selectedEventId) || SAMPLE_TIMELINE[3];
        setSnapshot(createSampleSnapshot(missionType, targetEv));
        appendLog(`SAMPLE \u6A21\u5F0F\u5207\u6362 Mission: ${missionType}`);
        return;
      }
      if (mode === "LIVE") {
        const cmd = { type: "SELECT_MISSION", mission_type: missionType };
        if (missionType === "RELAY_SOLVE_CUBE") {
          cmd.scramble_steps = selectedScrambleSteps;
        }
        void sendBackendCommand(cmd, `\u9009\u62E9 Mission ${missionType}`);
      }
    };
    const handleSelectScrambleSteps = (steps) => {
      setSelectedScrambleSteps(steps);
      if (mode === "LIVE") {
        void sendBackendCommand({ type: "SET_SCRAMBLE_STEPS", scramble_steps: steps }, `\u8BBE\u7F6E\u6253\u4E71\u6B65\u6570 ${steps}`);
      }
    };
    const handleRelayCommand = (cmd, label) => {
      if (mode !== "LIVE") {
        appendLog(`\u5F53\u524D\u4E3A ${mode} \u6A21\u5F0F\uFF0C\u4EC5 LIVE \u6A21\u5F0F\u652F\u6301\u5B9E\u65F6\u63A5\u529B\u63A7\u5236 [${label}]`);
        return;
      }
      void sendBackendCommand(cmd, label);
    };
    const openStartMissionModal = () => {
      if (mode === "LIVE" && snapshot.running) {
        appendLog("\u5F53\u524D\u5DF2\u6709\u4EFB\u52A1\u6B63\u5728\u8FD0\u884C\uFF0C\u8BF7\u5148\u70B9\u51FB\u300C\u5B89\u5168\u505C\u6B62\u300D\u540E\u518D\u542F\u52A8\u65B0\u4EFB\u52A1");
        return;
      }
      setStartModalPassword("");
      setStartModalError(null);
      setStartModalSubmitting(false);
      setStartModalOpen(true);
    };
    const closeStartMissionModal = () => {
      if (startModalSubmitting) return;
      setStartModalPassword("");
      setStartModalError(null);
      setStartModalOpen(false);
    };
    const handleLaunchMission = async (plannerMode) => {
      if (mode !== "LIVE") {
        setStartModalError(`\u5F53\u524D\u4E3A ${mode} \u53EA\u8BFB\u6A21\u5F0F\uFF0C\u4EC5 LIVE \u6A21\u5F0F\u652F\u6301\u6A21\u578B\u6821\u9A8C\u4E0E\u4EFB\u52A1\u542F\u52A8`);
        appendLog(`\u5F53\u524D\u4E3A ${mode} \u53EA\u8BFB\u6A21\u5F0F\uFF0C\u65E0\u6CD5\u542F\u52A8\u4EFB\u52A1 ${selectedMission}`);
        return;
      }
      if (plannerMode === "LLM_AGENT" && !startModalPassword) {
        setStartModalError("\u8BF7\u8F93\u5165\u542F\u7528\u5BC6\u7801\u4EE5\u542F\u7528 Agent \u6A21\u578B\u548C VLM \u6A21\u578B");
        startPasswordInputRef.current?.focus();
        return;
      }
      const suppliedPassword = startModalPassword;
      setStartModalSubmitting(true);
      setStartModalError(null);
      const modeCommand = {
        type: "SET_PLANNER_MODE",
        planner_mode: plannerMode
      };
      if (plannerMode === "LLM_AGENT") {
        modeCommand.enable_password = suppliedPassword;
      }
      const modeRes = await postBackendCommand(modeCommand);
      setStartModalPassword("");
      if (!modeRes.ok) {
        setStartModalSubmitting(false);
        if (modeRes.status === 403) {
          setStartModalError(`\u5BC6\u7801\u6821\u9A8C\u5931\u8D25\uFF0C\u672A\u80FD\u542F\u7528 Agent \u4E0E VLM \u6A21\u578B (${modeRes.detail || "HTTP 403"})`);
          appendLog(`\u540E\u7AEF\u62D2\u7EDD\u542F\u7528 Agent/VLM \u6A21\u578B: ${modeRes.detail || "HTTP 403"}`);
          window.setTimeout(() => startPasswordInputRef.current?.focus(), 0);
          return;
        }
        if (modeRes.status === 503) {
          setStartModalError(`\u670D\u52A1\u7AEF\u672A\u914D\u7F6E\u542F\u7528\u5BC6\u7801 (${modeRes.detail || "HTTP 503"})`);
          appendLog(`\u540E\u7AEF\u672A\u914D\u7F6E\u6A21\u578B\u542F\u7528\u5BC6\u7801: ${modeRes.detail || "HTTP 503"}`);
          return;
        }
        if (modeRes.status === 0) {
          setStartModalError(`\u65E0\u6CD5\u8FDE\u63A5\u540E\u7AEF\u670D\u52A1 (${getHttpBase()})\uFF0C\u8BF7\u786E\u8BA4\u4EFF\u771F\u540E\u7AEF\u5DF2\u8FD0\u884C`);
          appendLog(`\u542F\u52A8\u4EFB\u52A1\u5931\u8D25 [${selectedMission}]: MuJoCo \u540E\u7AEF\u672A\u8FDE\u63A5`);
          return;
        }
        setStartModalError(`\u5207\u6362\u89C4\u5212\u5668\u5931\u8D25 (${modeRes.detail || `HTTP ${modeRes.status}`})`);
        appendLog(`\u540E\u7AEF\u62D2\u7EDD\u5207\u6362 Planner: ${modeRes.detail || `HTTP ${modeRes.status}`}`);
        return;
      }
      if (modeRes.body?.snapshot?.running) {
        setStartModalSubmitting(false);
        setStartModalError("\u5F53\u524D\u5DF2\u6709\u4EFB\u52A1\u6B63\u5728\u8FD0\u884C\uFF0C\u8BF7\u5148\u70B9\u51FB\u300C\u5B89\u5168\u505C\u6B62\u300D");
        appendLog(`\u4EFB\u52A1\u542F\u52A8\u88AB\u8DF3\u8FC7 [${selectedMission}]: \u5F53\u524D\u5DF2\u6709\u4EFB\u52A1\u8FD0\u884C\u4E2D`);
        return;
      }
      const startCmd = {
        type: "START_MISSION",
        mission_type: selectedMission,
        seed: seedInput
      };
      if (selectedMission === "RELAY_SOLVE_CUBE") {
        startCmd.scramble_steps = selectedScrambleSteps;
        startCmd.full_26_cubie = true;
      }
      const startRes = await postBackendCommand(startCmd);
      setStartModalSubmitting(false);
      if (!startRes.ok) {
        const msg = startRes.status === 0 ? `\u65E0\u6CD5\u8FDE\u63A5\u540E\u7AEF\u670D\u52A1 (${getHttpBase()})\uFF0C\u8BF7\u786E\u8BA4\u4EFF\u771F\u540E\u7AEF\u5DF2\u8FD0\u884C` : `\u542F\u52A8\u4EFB\u52A1\u88AB\u62D2\u7EDD (${startRes.detail || `HTTP ${startRes.status}`})`;
        setStartModalError(msg);
        appendLog(`\u540E\u7AEF\u62D2\u7EDD\u6307\u4EE4 [\u542F\u52A8\u4EFB\u52A1 ${selectedMission}]: ${startRes.detail || `HTTP ${startRes.status}`}`);
        return;
      }
      if (startRes.body?.ok === false || startRes.body?.ack?.accepted === false) {
        const reason = String(startRes.body?.ack?.reason || "MISSION_NOT_ACCEPTED");
        setStartModalError(
          reason === "mission_already_running" ? "\u5F53\u524D\u5DF2\u6709\u4EFB\u52A1\u6B63\u5728\u8FD0\u884C\uFF0C\u8BF7\u5148\u70B9\u51FB\u300C\u5B89\u5168\u505C\u6B62\u300D" : `\u4EFB\u52A1\u672A\u542F\u52A8: ${reason}`
        );
        appendLog(`\u4EFB\u52A1\u672A\u542F\u52A8 [${selectedMission}]: ${reason}`);
        return;
      }
      setStartModalError(null);
      setStartModalOpen(false);
      appendLog(
        plannerMode === "LLM_AGENT" ? `\u5DF2\u901A\u8FC7\u5BC6\u7801\u542F\u7528 Agent + VLM \u6A21\u578B\u5E76\u542F\u52A8\u4EFB\u52A1 ${selectedMission} (seed=${seedInput})` : `\u5DF2\u4F7F\u7528\u786E\u5B9A\u6027 Baseline \u542F\u52A8\u4EFB\u52A1 ${selectedMission} (seed=${seedInput})`
      );
    };
    const toggleDebugFlag = (key, label) => {
      setDebugOverlays((prev) => {
        const next = { ...prev, [key]: !prev[key] };
        if (mode === "LIVE" && wsConnected) {
          void sendBackendCommand({ type: "SET_RENDER_FLAGS", flags: next }, `\u5207\u6362\u6E32\u67D3\u8C03\u8BD5\u5C42 ${label}`);
        }
        return next;
      });
    };
    const handleLoadReplayFiles = async (videoFile, timingFile) => {
      if (videoFile) {
        setReplayVideoUrl(URL.createObjectURL(videoFile));
        appendLog(`\u5DF2\u8F7D\u5165\u5386\u53F2\u5F55\u50CF: ${videoFile.name}`);
      }
      if (timingFile) {
        try {
          const text = await timingFile.text();
          const parsed = JSON.parse(text);
          setReplayTiming(parsed);
          setSnapshot((prev) => ({
            ...prev,
            session_id: parsed.session_id,
            seed: parsed.seed,
            timeline: parsed.timeline || [],
            trace_events: parsed.trace_events || [],
            observations: parsed.observations || []
          }));
          appendLog(`\u5DF2\u8F7D\u5165\u65F6\u95F4\u8F74\u5143\u6570\u636E: ${timingFile.name}`);
        } catch {
          appendLog(`\u89E3\u6790 ${timingFile.name} \u5931\u8D25`);
        }
      }
    };
    const handleReplayTimeUpdate = (videoTimeSec) => {
      if (mode !== "REPLAY" || !replayTiming?.frames?.length) return;
      let matched = replayTiming.frames[0];
      for (const f of replayTiming.frames) {
        if (f.video_time_sec <= videoTimeSec) matched = f;
        else break;
      }
      setSnapshot((prev) => ({
        ...prev,
        sim_time: matched.sim_time,
        current_stage_id: matched.current_stage_id,
        current_skill: matched.current_skill,
        task_status: matched.task_status,
        observed_facelets: matched.observed_facelets,
        predicted_facelets: matched.predicted_facelets,
        cube_validation_status: matched.cube_validation_status,
        telemetry: matched.telemetry
      }));
    };
    const handleTimelineEventClick = (ev) => {
      if (mode === "LIVE") {
        appendLog("LIVE \u6A21\u5F0F\u4E0B\u65F6\u95F4\u7EBF\u4E3A\u53EA\u8BFB\u5BA1\u8BA1\u6D41\uFF0C\u7981\u6B62\u56DE\u6EAF\u7BE1\u6539\u7269\u7406\u4EFF\u771F\u72B6\u6001");
        return;
      }
      setSelectedEventId(ev.event_id);
      if (mode === "SAMPLE") {
        const nextSnap = createSampleSnapshot(selectedMission, ev);
        nextSnap.active_camera = snapshot.active_camera;
        setSnapshot(nextSnap);
      } else if (mode === "REPLAY" && replayVideoRef.current && replayTiming?.frames?.length) {
        const target = replayTiming.frames.find((f) => f.sim_time >= ev.sim_time);
        if (target) replayVideoRef.current.currentTime = target.video_time_sec;
      }
    };
    const refreshExportRuns = async () => {
      setExportErrorMsg(null);
      if (mode === "SAMPLE" || snapshot.frame_source === "SYNTHETIC_SAMPLE") {
        setExportRuns([]);
        return;
      }
      try {
        const resp = await fetch(`${getHttpBase()}/api/m3d/runs`);
        if (!resp.ok) {
          setExportErrorMsg(`\u83B7\u53D6\u5386\u53F2\u5B9E\u9A8C\u5217\u8868\u5931\u8D25: HTTP ${resp.status}`);
          return;
        }
        const data = await resp.json();
        const runs = Array.isArray(data.runs) ? data.runs : [];
        setExportRuns(runs);
        const preferred = data.current_run_id || snapshot.run_id || (runs[0]?.run_id ?? "");
        if (preferred && !exportSelectedRunId) {
          setExportSelectedRunId(preferred);
        }
      } catch {
        setExportErrorMsg("\u65E0\u6CD5\u8FDE\u63A5\u540E\u7AEF\u83B7\u53D6\u5386\u53F2\u5B9E\u9A8C\u8FD0\u884C\u5217\u8868\uFF08\u8BF7\u786E\u8BA4 LIVE \u670D\u52A1\u5DF2\u542F\u52A8\uFF09");
      }
    };
    const openExportModal = () => {
      setExportModalOpen(true);
      setExportErrorMsg(null);
      if (snapshot.run_id) {
        setExportSelectedRunId(snapshot.run_id);
      }
      if (mode !== "SAMPLE") {
        void refreshExportRuns();
      }
    };
    const handleDownloadExperimentZip = async () => {
      setExportStatusMsg(null);
      setExportErrorMsg(null);
      if (mode === "SAMPLE" || snapshot.frame_source === "SYNTHETIC_SAMPLE") {
        setExportErrorMsg("SAMPLE_MODE_FORBIDDEN: SYNTHETIC_SAMPLE \u4EC5\u7528\u4E8E\u79BB\u7EBF\u6F14\u793A\uFF0C\u7981\u6B62\u4F5C\u4E3A\u771F\u5B9E\u7269\u7406\u5B9E\u9A8C\u5BFC\u51FA");
        return;
      }
      const targetRunId = (exportSelectedRunId || snapshot.run_id || "").trim() || null;
      setExportSubmitting(true);
      try {
        const resp = await fetch(`${getHttpBase()}/api/m3d/export`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            run_id: targetRunId,
            scope: exportScope,
            include_rgbd: exportIncludeRgbd,
            include_high_freq_trajectory: exportIncludeHighFreq,
            include_audit_ground_truth: exportIncludeAuditTruth
          })
        });
        if (!resp.ok) {
          const errBody = await resp.json().catch(() => null);
          const detail = typeof errBody?.detail === "string" ? errBody.detail : `HTTP ${resp.status}`;
          setExportErrorMsg(`\u5BFC\u51FA\u5931\u8D25: ${detail}`);
          appendLog(`\u5B9E\u9A8C\u5305\u5BFC\u51FA\u5931\u8D25: ${detail}`);
          return;
        }
        const blob = await resp.blob();
        const disp = resp.headers.get("Content-Disposition") || "";
        const match = /filename="([^"]+)"/.exec(disp);
        const filename = match ? match[1] : `cuberelay_${targetRunId || "export"}_${exportScope}.zip`;
        const objectUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = objectUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(objectUrl);
        const kb = (blob.size / 1024).toFixed(1);
        setExportStatusMsg(`\u5DF2\u5BFC\u51FA ${filename} (${kb} KB)`);
        appendLog(`\u5DF2\u4ECE\u540E\u7AEF\u5BFC\u51FA\u5B8C\u6574\u5B9E\u9A8C\u5305: ${filename} (${kb} KB)`);
      } catch {
        setExportErrorMsg("\u5BFC\u51FA\u5931\u8D25: \u540E\u7AEF\u8FDE\u63A5\u4E0D\u53EF\u7528\u6216\u8BF7\u6C42\u88AB\u4E2D\u65AD");
      } finally {
        setExportSubmitting(false);
      }
    };
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "h-screen w-screen overflow-hidden bg-[#080D16] text-slate-100 flex flex-col font-sans select-none", children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("header", { className: "h-11 shrink-0 bg-[#101827] border-b border-slate-800/90 px-3.5 flex items-center justify-between gap-3", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-4", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-2", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "w-6 h-6 rounded bg-[#182338] border border-[#3DE8E5]/40 flex items-center justify-center", children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Cpu, { className: "w-3.5 h-3.5 text-[#3DE8E5]" }) }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-xs font-bold tracking-wider text-slate-100", children: "CUBERELAY" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[10px] font-mono px-1.5 py-0.2 rounded bg-[#182338] text-[#3DE8E5] border border-slate-700", children: "M3-D" })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("nav", { className: "flex items-center gap-1", children: [
            { id: "CONSOLE", label: "\u4EFB\u52A1\u63A7\u5236\u53F0" },
            { id: "SETTINGS", label: "\u80FD\u529B\u6CE8\u518C\u8868 & \u8BBE\u7F6E" },
            { id: "BENCHMARK", label: "Task Agent \u8BC4\u4F30" }
          ].map((tab) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            "button",
            {
              type: "button",
              onClick: () => setActiveNav(tab.id),
              className: `px-2.5 py-1 rounded text-[11px] font-medium transition-colors ${activeNav === tab.id ? "bg-[#182338] text-[#3DE8E5] border border-[#3DE8E5]/30" : "text-slate-400 hover:text-slate-200"}`,
              children: tab.label
            },
            tab.id
          )) })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "hidden lg:flex items-center gap-2 text-[11px] font-mono tracking-widest text-slate-400", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: selectedMission }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-600", children: "|" }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[#3DE8E5]", children: snapshot.session_id })
        ] }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-2", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center bg-[#080D16] p-0.5 rounded border border-slate-800 text-[11px]", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
              "button",
              {
                type: "button",
                onClick: () => handleSwitchMode("SAMPLE"),
                className: `px-2 py-0.5 rounded font-medium flex items-center gap-1 transition-colors ${mode === "SAMPLE" ? "bg-[#FFBF69]/20 text-[#FFBF69] border border-[#FFBF69]/40" : "text-slate-400 hover:text-slate-200"}`,
                children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Database, { className: "w-3 h-3" }),
                  " SYNTHETIC SAMPLE"
                ]
              }
            ),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
              "button",
              {
                type: "button",
                onClick: () => handleSwitchMode("LIVE"),
                className: `px-2 py-0.5 rounded font-medium flex items-center gap-1 transition-colors ${mode === "LIVE" ? "bg-[#30D6A0]/20 text-[#30D6A0] border border-[#30D6A0]/40" : "text-slate-400 hover:text-slate-200"}`,
                children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Radio, { className: "w-3 h-3" }),
                  " LIVE \u5B9E\u65F6\u4EFF\u771F"
                ]
              }
            ),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
              "button",
              {
                type: "button",
                onClick: () => handleSwitchMode("REPLAY"),
                className: `px-2 py-0.5 rounded font-medium flex items-center gap-1 transition-colors ${mode === "REPLAY" ? "bg-[#548CFF]/20 text-[#548CFF] border border-[#548CFF]/40" : "text-slate-400 hover:text-slate-200"}`,
                children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(History, { className: "w-3 h-3" }),
                  " PREVIEW \u79BB\u7EBF\u9884\u89C8"
                ]
              }
            )
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "hidden sm:flex items-center gap-1.5 text-[11px] font-mono text-slate-300 bg-[#080D16] px-2 py-0.5 rounded border border-slate-800", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Clock, { className: "w-3 h-3 text-[#3DE8E5]" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
              formatSimTime(snapshot.sim_time),
              "s"
            ] })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
            "button",
            {
              type: "button",
              onClick: openExportModal,
              className: "inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium bg-[#182338] hover:bg-slate-700 text-[#3DE8E5] border border-[#3DE8E5]/30 transition-colors",
              title: "Experiment / Trace Export (\u540E\u7AEF\u771F\u5B9E\u5B9E\u9A8C\u5305 ZIP \u5BFC\u51FA)",
              children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Download, { className: "w-3 h-3" }),
                " \u5B9E\u9A8C\u5BFC\u51FA"
              ]
            }
          ),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            "button",
            {
              type: "button",
              onClick: () => setActiveNav(activeNav === "SETTINGS" ? "CONSOLE" : "SETTINGS"),
              className: "p-1.5 rounded bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700/80",
              title: "\u80FD\u529B\u6CE8\u518C\u8868\u4E0E\u7CFB\u7EDF\u8BBE\u7F6E",
              children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Settings, { className: "w-3.5 h-3.5" })
            }
          )
        ] })
      ] }),
      activeNav === "SETTINGS" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
        CapabilityAndSettingsView,
        {
          wsUrl,
          onWsUrlChange: setWsUrl,
          seedInput,
          onSeedChange: setSeedInput,
          capabilities: snapshot.capabilities,
          commandLog
        }
      ),
      activeNav === "BENCHMARK" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(TaskAgentBenchmarkView, { httpBase: getHttpBase() }),
      activeNav === "CONSOLE" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("main", { className: "flex-1 min-h-0 p-2.5 flex flex-col gap-2", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
          "div",
          {
            style: { gridTemplateColumns: "minmax(0, 1.65fr) minmax(360px, 1fr)" },
            className: "flex-1 min-h-0 grid gap-2.5",
            children: [
              /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "min-w-0 min-h-0 h-full flex flex-col gap-2", children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "flex-1 min-h-0", children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                  SimulationViewport,
                  {
                    mode,
                    wsConnected,
                    wsUrl,
                    snapshot,
                    debugOverlays,
                    onCameraPresetChange: (preset) => {
                      const found = CAMERA_PRESETS.find((c) => c.id === preset);
                      setSnapshot((prev) => ({
                        ...prev,
                        active_camera: preset,
                        camera_azimuth_deg: found?.az ?? prev.camera_azimuth_deg,
                        camera_elevation_deg: found?.el ?? prev.camera_elevation_deg,
                        camera_distance_m: found?.dist ?? prev.camera_distance_m
                      }));
                      if (mode === "LIVE") {
                        void sendBackendCommand({ type: "SET_CAMERA_PRESET", camera: preset }, `\u5207\u6362\u76F8\u673A ${preset}`);
                      }
                    },
                    onCameraOrbitCommand: (dAz, dEl) => {
                      void sendBackendCommand(
                        { type: "CAMERA_ORBIT", delta_azimuth: dAz, delta_elevation: dEl },
                        "\u65CB\u8F6C\u76F8\u673A\u89C6\u89D2"
                      );
                    },
                    onCameraZoomCommand: (dDist) => {
                      void sendBackendCommand({ type: "CAMERA_ZOOM", delta_distance: dDist }, "\u7F29\u653E\u76F8\u673A\u89C6\u89D2");
                    },
                    previewScreenshotUrl,
                    onUploadPreviewScreenshot: (url) => {
                      setPreviewScreenshotUrl(url);
                      appendLog("\u5DF2\u5728 PREVIEW \u6A21\u5F0F\u8F7D\u5165\u5916\u90E8\u5386\u53F2\u622A\u56FE");
                    },
                    replayVideoRef,
                    replayVideoUrl,
                    onReplayTimeUpdate: handleReplayTimeUpdate,
                    onLoadReplayFiles: handleLoadReplayFiles,
                    onUrgentInterrupt: () => handleRelayCommand({ type: "URGENT_INTERRUPT", reason: "\u6A2A\u5E45\u7D27\u6025\u5239\u8F66/\u63A5\u7BA1" }, "\u7D27\u6025\u5239\u8F66\u4E2D\u65AD")
                  }
                ) }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "shrink-0 bg-[#101827] border border-slate-800/90 rounded-lg px-2.5 py-1.5 space-y-2", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
                    "button",
                    {
                      type: "button",
                      onClick: () => setTechDrawerOpen((v) => !v),
                      className: "w-full flex items-center justify-between gap-2 text-[10.5px] font-medium text-slate-300 hover:text-white transition-colors",
                      children: [
                        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "flex items-center gap-2 min-w-0 truncate", children: [
                          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "font-semibold text-[#3DE8E5]", children: [
                            techDrawerOpen ? "\u25BE" : "\u25B8",
                            " \u673A\u5668\u4EBA\u76F8\u673A \xB7 Cube State \xB7 \u9065\u6D4B\u76D1\u63A7"
                          ] }),
                          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "font-mono text-[10px] text-slate-400 truncate", children: [
                            "(",
                            snapshot.observed_facelets.filter((f) => f.color !== "UNKNOWN").length,
                            "/54 \u683C \xB7 \u5939\u722A",
                            " ",
                            snapshot.telemetry.gripperState || "UNKNOWN",
                            ")"
                          ] })
                        ] }),
                        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "px-1.5 py-0.5 rounded bg-[#080D16] border border-slate-800 text-[9.5px] font-mono text-slate-400 shrink-0", children: techDrawerOpen ? "\u6536\u8D77\u76D1\u63A7 \u25B4" : "\u5C55\u5F00\u76D1\u63A7 \u25BE" })
                      ]
                    }
                  ),
                  techDrawerOpen && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "h-[210px] grid grid-cols-1 md:grid-cols-3 gap-2.5", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                      CompactRobotCameraCard,
                      {
                        rgbUrl: snapshot.wrist_rgb_url,
                        depthUrl: snapshot.wrist_depth_url,
                        depthRangeM: snapshot.depth_range_m,
                        detections: snapshot.detections
                      }
                    ),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                      CompactCubeStateCard,
                      {
                        observed: snapshot.observed_facelets,
                        predicted: snapshot.predicted_facelets,
                        validationStatus: snapshot.cube_validation_status
                      }
                    ),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CompactTelemetryCard, { telemetry: snapshot.telemetry })
                  ] })
                ] })
              ] }),
              /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                RightOrchestrationPanel,
                {
                  mode,
                  snapshot,
                  selectedMission,
                  selectedScrambleSteps,
                  onSelectMission: handleSelectMission,
                  onSelectScrambleSteps: handleSelectScrambleSteps,
                  onRelayCommand: handleRelayCommand
                }
              )
            ]
          }
        ),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("footer", { className: "h-10 shrink-0 bg-[#101827] border border-slate-800/90 rounded-lg px-3 flex items-center justify-between gap-3", children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1.5 overflow-x-auto min-w-0 py-0.5", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[10px] font-mono text-slate-500 shrink-0 mr-0.5", children: "TIMELINE:" }),
            snapshot.timeline.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-[11px] font-mono text-slate-500", children: "00:00.00 \xB7 IDLE" }) : snapshot.timeline.map((ev) => {
              const active = ev.event_id === selectedEventId;
              return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                "button",
                {
                  type: "button",
                  onClick: () => handleTimelineEventClick(ev),
                  className: `px-2 py-0.5 rounded text-[11px] font-mono shrink-0 border transition-colors ${active ? "bg-[#182338] text-[#3DE8E5] border-[#3DE8E5]/50" : "bg-[#080D16] text-slate-400 border-slate-800 hover:text-slate-200"}`,
                  children: ev.short_label
                },
                ev.event_id
              );
            })
          ] }),
          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1.5 shrink-0", children: [
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "button",
              {
                type: "button",
                onClick: () => toggleDebugFlag("contactForces", "\u63A5\u89E6\u529B"),
                className: `hidden xl:inline-flex px-2 py-1 rounded text-[11px] border transition-colors ${debugOverlays.contactForces ? "bg-[#FFBF69]/15 text-[#FFBF69] border-[#FFBF69]/40" : "bg-[#080D16] text-slate-400 border-slate-800"}`,
                children: "\u63A5\u89E6\u529B"
              }
            ),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
              "button",
              {
                type: "button",
                onClick: () => toggleDebugFlag("collisionGeoms", "\u78B0\u649E\u70B9"),
                className: `hidden xl:inline-flex px-2 py-1 rounded text-[11px] border transition-colors ${debugOverlays.collisionGeoms ? "bg-[#548CFF]/15 text-[#548CFF] border-[#548CFF]/40" : "bg-[#080D16] text-slate-400 border-slate-800"}`,
                children: "\u78B0\u649E\u70B9"
              }
            ),
            /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "h-4 w-px bg-slate-800 mx-0.5 hidden xl:block" }),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
              "button",
              {
                type: "button",
                onClick: openStartMissionModal,
                disabled: mode === "LIVE" && snapshot.running,
                title: mode !== "LIVE" ? "\u8BF7\u5207\u6362\u81F3 LIVE \u5B9E\u65F6\u4EFF\u771F\u6A21\u5F0F\u8FDE\u63A5\u540E\u7AEF\u540E\u542F\u52A8" : snapshot.running ? "\u5F53\u524D\u4EFB\u52A1\u6B63\u5728\u8FD0\u884C\u4E2D\uFF0C\u8BF7\u5148\u70B9\u51FB\u300C\u5B89\u5168\u505C\u6B62\u300D" : `\u542F\u52A8\u524D\u8F93\u5165\u5BC6\u7801\u542F\u7528 Agent \u4E0E VLM \u6A21\u578B: ${selectedMission}`,
                className: "inline-flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-semibold bg-[#30D6A0]/20 hover:bg-[#30D6A0]/30 text-[#30D6A0] border border-[#30D6A0]/50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
                children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Play, { className: "w-3 h-3" }),
                  " \u5F00\u59CB\u4EFB\u52A1 (",
                  MISSION_OPTIONS.find((m) => m.type === selectedMission)?.label,
                  ")"
                ]
              }
            ),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
              "button",
              {
                type: "button",
                onClick: () => void sendBackendCommand({ type: "STOP_MISSION" }, "\u5B89\u5168\u505C\u6B62\u4EFB\u52A1"),
                className: "inline-flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-semibold bg-[#FF667B]/15 hover:bg-[#FF667B]/25 text-[#FF667B] border border-[#FF667B]/40 transition-colors",
                children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Square, { className: "w-3 h-3" }),
                  " \u5B89\u5168\u505C\u6B62"
                ]
              }
            ),
            /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
              "button",
              {
                type: "button",
                onClick: () => void sendBackendCommand(
                  {
                    type: "RESET_SCENE",
                    seed: seedInput,
                    mission_type: selectedMission,
                    ...selectedMission === "RELAY_SOLVE_CUBE" ? { scramble_steps: selectedScrambleSteps, full_26_cubie: true } : {}
                  },
                  `\u91CD\u7F6E\u573A\u666F (seed=${seedInput}, mission=${selectedMission})`
                ),
                className: "inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium bg-[#182338] hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors",
                children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RotateCcw, { className: "w-3 h-3" }),
                  " \u91CD\u7F6E\u573A\u666F"
                ]
              }
            )
          ] })
        ] }),
        startModalOpen && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
          "div",
          {
            className: "fixed inset-0 z-40 bg-black/50 flex items-end justify-end p-3 pb-14",
            onClick: closeStartMissionModal,
            children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
              "div",
              {
                role: "dialog",
                "aria-modal": "true",
                "aria-labelledby": "start-mission-modal-title",
                onClick: (e) => e.stopPropagation(),
                className: "w-full max-w-sm bg-[#101827] border border-[#3DE8E5]/40 rounded-lg p-3.5 space-y-2.5 shadow-2xl",
                children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-2 border-b border-slate-800 pb-2", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1.5 min-w-0", children: [
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Lock, { className: "w-3.5 h-3.5 text-[#3DE8E5] shrink-0" }),
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { id: "start-mission-modal-title", className: "text-xs font-semibold text-slate-100 truncate", children: "\u542F\u52A8\u524D\u5BC6\u7801\u542F\u7528 Agent & VLM \u6A21\u578B" })
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                      "button",
                      {
                        type: "button",
                        "aria-label": "\u5173\u95ED\u5F39\u7A97",
                        disabled: startModalSubmitting,
                        onClick: closeStartMissionModal,
                        className: "p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-[#182338] transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
                        children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(X, { className: "w-3.5 h-3.5" })
                      }
                    )
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#080D16] border border-slate-800 rounded p-2 space-y-1 text-[10.5px]", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-2", children: [
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-400", children: "\u5F85\u542F\u52A8\u4EFB\u52A1" }),
                      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "font-mono text-[#3DE8E5]", children: [
                        MISSION_OPTIONS.find((m) => m.type === selectedMission)?.label,
                        " \xB7 Seed ",
                        seedInput
                      ] })
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "grid grid-cols-2 gap-1.5 pt-1 border-t border-slate-800/80", children: [
                      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "rounded border border-[#3DE8E5]/30 bg-[#3DE8E5]/5 px-1.5 py-1", children: [
                        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[9px] font-mono text-[#3DE8E5]", children: "VLM \u6A21\u578B \xB7 \u611F\u77E5" }),
                        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] text-slate-200 truncate", children: snapshot.agent_state?.perception_model_name || "Visual Perception" })
                      ] }),
                      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "rounded border border-[#548CFF]/30 bg-[#548CFF]/5 px-1.5 py-1", children: [
                        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[9px] font-mono text-[#548CFF]", children: "Agent \u6A21\u578B \xB7 \u89C4\u5212" }),
                        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[10px] text-slate-200 truncate", children: snapshot.agent_state?.agent_model_name || "Action Planner" })
                      ] })
                    ] })
                  ] }),
                  mode !== "LIVE" && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#FFBF69]/10 border border-[#FFBF69]/40 rounded px-2 py-1.5 text-[10.5px] text-[#FFBF69] leading-snug flex items-center justify-between gap-2", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                      "\u5F53\u524D\u4E3A ",
                      mode,
                      " \u53EA\u8BFB\u6A21\u5F0F\uFF0C\u9700\u5207\u6362\u81F3 LIVE \u6A21\u5F0F\u540E\u542F\u52A8\u3002"
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                      "button",
                      {
                        type: "button",
                        onClick: () => {
                          handleSwitchMode("LIVE");
                          setStartModalError(null);
                        },
                        className: "px-2 py-0.5 rounded text-[10px] font-semibold bg-[#30D6A0]/20 text-[#30D6A0] border border-[#30D6A0]/40 shrink-0",
                        children: "\u5207\u6362 LIVE"
                      }
                    )
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
                    "form",
                    {
                      className: "space-y-2",
                      onSubmit: (e) => {
                        e.preventDefault();
                        void handleLaunchMission("LLM_AGENT");
                      },
                      children: [
                        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-1", children: [
                          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("label", { htmlFor: "start-model-enable-password", className: "block text-[10.5px] text-slate-300", children: "\u6A21\u578B\u542F\u7528\u5BC6\u7801\uFF08\u6BCF\u6B21\u542F\u52A8\u524D\u6821\u9A8C\u5E76\u542F\u7528 Agent \u4E0E VLM \u6A21\u578B\uFF09" }),
                          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                            "input",
                            {
                              id: "start-model-enable-password",
                              ref: startPasswordInputRef,
                              type: "password",
                              value: startModalPassword,
                              autoComplete: "current-password",
                              "aria-label": "Agent \u4E0E VLM \u6A21\u578B\u542F\u7528\u5BC6\u7801",
                              placeholder: "\u8F93\u5165\u5BC6\u7801\u542F\u7528 Agent \u6A21\u578B\u548C VLM \u6A21\u578B",
                              disabled: startModalSubmitting,
                              onChange: (e) => {
                                setStartModalPassword(e.target.value);
                                if (startModalError) setStartModalError(null);
                              },
                              className: "w-full rounded border border-slate-700 bg-[#080D16] px-2.5 py-1.5 text-[11px] text-slate-100 outline-none focus:border-[#30D6A0] placeholder:text-slate-600"
                            }
                          ),
                          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "text-[9.5px] leading-tight text-slate-500", children: "\u5BC6\u7801\u4EC5\u7528\u4E8E\u672C\u6B21\u540E\u7AEF\u6821\u9A8C\uFF0C\u4E0D\u4F1A\u5199\u5165\u4EFB\u52A1 Trace \u6216\u9875\u9762\u5FEB\u7167\u3002" })
                        ] }),
                        startModalError && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "bg-[#FF667B]/10 border border-[#FF667B]/40 rounded px-2 py-1.5 text-[10.5px] text-[#FF667B] leading-snug", children: startModalError }),
                        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-2 pt-1 border-t border-slate-800", children: [
                          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                            "button",
                            {
                              type: "button",
                              disabled: startModalSubmitting || mode !== "LIVE",
                              onClick: () => void handleLaunchMission("DETERMINISTIC_PLANNER"),
                              className: "shrink-0 px-2 py-1.5 rounded text-[10.5px] font-medium bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
                              children: "\u786E\u5B9A\u6027 Baseline \u542F\u52A8"
                            }
                          ),
                          /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1.5 shrink-0", children: [
                            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                              "button",
                              {
                                type: "button",
                                disabled: startModalSubmitting,
                                onClick: closeStartMissionModal,
                                className: "shrink-0 px-2.5 py-1.5 rounded text-[11px] font-medium bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
                                children: "\u53D6\u6D88"
                              }
                            ),
                            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                              "button",
                              {
                                type: "submit",
                                disabled: startModalSubmitting || !startModalPassword || mode !== "LIVE",
                                className: "shrink-0 inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded text-[11px] font-semibold bg-[#30D6A0]/20 hover:bg-[#30D6A0]/30 text-[#30D6A0] border border-[#30D6A0]/50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
                                children: startModalSubmitting ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
                                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RefreshCw, { className: "w-3 h-3 animate-spin" }),
                                  " \u6821\u9A8C\u4E2D..."
                                ] }) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
                                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Play, { className: "w-3 h-3" }),
                                  " \u542F\u7528\u5E76\u5F00\u59CB\u4EFB\u52A1"
                                ] })
                              }
                            )
                          ] })
                        ] })
                      ]
                    }
                  )
                ]
              }
            )
          }
        )
      ] }),
      exportModalOpen && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
        "div",
        {
          className: "fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-3",
          onClick: () => {
            if (!exportSubmitting) setExportModalOpen(false);
          },
          children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
            "div",
            {
              role: "dialog",
              "aria-modal": "true",
              "aria-labelledby": "experiment-export-modal-title",
              onClick: (e) => e.stopPropagation(),
              className: "w-full max-w-md bg-[#101827] border border-[#3DE8E5]/40 rounded-lg p-3.5 space-y-2.5 shadow-2xl",
              children: [
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-2 border-b border-slate-800 pb-2", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center gap-1.5 min-w-0", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Download, { className: "w-3.5 h-3.5 text-[#3DE8E5] shrink-0" }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { id: "experiment-export-modal-title", className: "text-xs font-semibold text-slate-100 truncate", children: "Experiment / Trace Export \xB7 \u56E0\u679C\u5BA1\u8BA1\u5B9E\u9A8C\u5305" })
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                    "button",
                    {
                      type: "button",
                      "aria-label": "\u5173\u95ED\u5BFC\u51FA\u5F39\u7A97",
                      disabled: exportSubmitting,
                      onClick: () => setExportModalOpen(false),
                      className: "p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-[#182338] transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
                      children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(X, { className: "w-3.5 h-3.5" })
                    }
                  )
                ] }),
                mode === "SAMPLE" || snapshot.frame_source === "SYNTHETIC_SAMPLE" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "bg-[#FF667B]/10 border border-[#FF667B]/40 rounded p-2 text-[10.5px] text-[#FF667B] leading-snug", children: "\u5F53\u524D\u4E3A SYNTHETIC_SAMPLE \u5408\u6210\u6F14\u793A\u6A21\u5F0F\uFF1ASAMPLE \u6570\u636E\u4E25\u7981\u4F5C\u4E3A\u771F\u5B9E\u7269\u7406\u5B9E\u9A8C\u6570\u636E\u5305\u5BFC\u51FA\uFF0C\u8BF7\u5207\u6362\u81F3 LIVE \u5B9E\u65F6\u4EFF\u771F\u3002" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "bg-[#080D16] border border-slate-800 rounded p-2 space-y-1 text-[10.5px]", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-2", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-400", children: "\u5F53\u524D run_id" }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "font-mono text-[#3DE8E5] truncate", children: snapshot.run_id || "\u672A\u521B\u5EFA\u8FD0\u884C\u8BB0\u5F55" })
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between gap-2", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "text-slate-400", children: "\u6570\u636E\u91C7\u96C6\u72B6\u6001" }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "font-mono text-[#30D6A0]", children: snapshot.experiment_recording?.status || "IDLE" })
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "grid grid-cols-3 gap-1 pt-1 border-t border-slate-800/80 font-mono text-[9.5px] text-slate-300", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                      "Frames: ",
                      snapshot.experiment_recording?.counts?.frames ?? 0
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                      "Poses: ",
                      snapshot.experiment_recording?.counts?.pose_estimates ?? 0
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                      "Targets: ",
                      snapshot.experiment_recording?.counts?.grasp_targets ?? 0
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                      "States: ",
                      snapshot.experiment_recording?.counts?.robot_states ?? 0
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                      "Contacts: ",
                      snapshot.experiment_recording?.counts?.contact_samples ?? 0
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
                      "Verifs: ",
                      snapshot.experiment_recording?.counts?.contact_verifications ?? 0
                    ] })
                  ] })
                ] }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-2 text-[10.5px]", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-1", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-between", children: [
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("label", { htmlFor: "export-run-select", className: "text-slate-300", children: "\u5386\u53F2\u5B9E\u9A8C\u8FD0\u884C\u5217\u8868 (\u6309 run_id \u5BFC\u51FA)" }),
                      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
                        "button",
                        {
                          type: "button",
                          onClick: () => void refreshExportRuns(),
                          disabled: mode === "SAMPLE" || exportSubmitting,
                          className: "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9.5px] bg-[#182338] text-slate-300 border border-slate-700 hover:text-white disabled:opacity-40",
                          children: [
                            /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RefreshCw, { className: "w-2.5 h-2.5" }),
                            " \u5237\u65B0\u5217\u8868"
                          ]
                        }
                      )
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
                      "select",
                      {
                        id: "export-run-select",
                        value: exportSelectedRunId,
                        disabled: mode === "SAMPLE" || exportSubmitting,
                        onChange: (e) => setExportSelectedRunId(e.target.value),
                        className: "w-full rounded border border-slate-700 bg-[#080D16] px-2 py-1 text-[10.5px] font-mono text-slate-100 outline-none focus:border-[#30D6A0]",
                        children: [
                          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "", children: snapshot.run_id ? `\u5F53\u524D\u8FD0\u884C (${snapshot.run_id})` : "\u5F53\u524D\u6700\u65B0\u8FD0\u884C" }),
                          exportRuns.map((run) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("option", { value: run.run_id, children: [
                            run.run_id,
                            " \xB7 ",
                            run.mission_type || "MISSION",
                            " \xB7 seed=",
                            run.seed ?? 0,
                            " \xB7 ",
                            run.recording_status || "READY"
                          ] }, run.run_id))
                        ]
                      }
                    )
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-1", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsx)("label", { htmlFor: "export-scope-select", className: "block text-slate-300", children: "\u5BFC\u51FA\u8303\u56F4" }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
                      "select",
                      {
                        id: "export-scope-select",
                        value: exportScope,
                        disabled: mode === "SAMPLE" || exportSubmitting,
                        onChange: (e) => setExportScope(e.target.value),
                        className: "w-full rounded border border-slate-700 bg-[#080D16] px-2 py-1 text-[10.5px] font-mono text-slate-100 outline-none focus:border-[#30D6A0]",
                        children: [
                          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "full_mission", children: "full_mission\uFF08\u5B8C\u6574 Mission + \u89C6\u89C9 + \u8F68\u8FF9 + \u63A5\u89E6\u9A8C\u8BC1\uFF09" }),
                          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "grasp_causal_chain", children: "grasp_causal_chain\uFF08\u6293\u53D6\u89C6\u89C9\u56E0\u679C\u94FE\u4E13\u9879\u5305\uFF09" }),
                          /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", { value: "events_only", children: "events_only\uFF08\u4EC5\u4E8B\u4EF6\u6D41 / Snapshot / \u6821\u9A8C\u62A5\u544A\uFF09" })
                        ]
                      }
                    )
                  ] }),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "space-y-1 bg-[#080D16] border border-slate-800 rounded p-2", children: [
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { className: "flex items-center gap-2 text-slate-300", children: [
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                        "input",
                        {
                          type: "checkbox",
                          checked: exportIncludeRgbd,
                          disabled: mode === "SAMPLE" || exportSubmitting,
                          onChange: (e) => setExportIncludeRgbd(e.target.checked)
                        }
                      ),
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "\u5305\u542B\u539F\u59CB RGB (.png) \u4E0E\u7C73\u5236 Depth (.npy) + \u6807\u5B9A\u5185/\u5916\u53C2" })
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { className: "flex items-center gap-2 text-slate-300", children: [
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                        "input",
                        {
                          type: "checkbox",
                          checked: exportIncludeHighFreq,
                          disabled: mode === "SAMPLE" || exportSubmitting,
                          onChange: (e) => setExportIncludeHighFreq(e.target.checked)
                        }
                      ),
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "\u5305\u542B\u9AD8\u9891\u673A\u5668\u4EBA\u8F68\u8FF9\u4E0E\u63A5\u89E6\u65F6\u5E8F (robot_states / contact_samples)" })
                    ] }),
                    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", { className: "flex items-center gap-2 text-slate-300", children: [
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                        "input",
                        {
                          type: "checkbox",
                          checked: exportIncludeAuditTruth,
                          disabled: mode === "SAMPLE" || exportSubmitting,
                          onChange: (e) => setExportIncludeAuditTruth(e.target.checked)
                        }
                      ),
                      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "\u5305\u542B\u9694\u79BB\u5BA1\u8BA1\u771F\u503C (audit_only_poses.csv\uFF0C\u4EC5\u79BB\u7EBF\u5BA1\u8BA1\u7528)" })
                    ] })
                  ] })
                ] }),
                exportStatusMsg && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "bg-[#30D6A0]/15 border border-[#30D6A0]/40 rounded px-2 py-1.5 text-[10.5px] text-[#30D6A0] leading-snug", children: exportStatusMsg }),
                exportErrorMsg && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "bg-[#FF667B]/10 border border-[#FF667B]/40 rounded px-2 py-1.5 text-[10.5px] text-[#FF667B] leading-snug", children: exportErrorMsg }),
                /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "flex items-center justify-end gap-2 pt-1 border-t border-slate-800", children: [
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                    "button",
                    {
                      type: "button",
                      disabled: exportSubmitting,
                      onClick: () => setExportModalOpen(false),
                      className: "px-2.5 py-1.5 rounded text-[11px] font-medium bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors disabled:opacity-40",
                      children: "\u5173\u95ED"
                    }
                  ),
                  /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
                    "button",
                    {
                      type: "button",
                      disabled: exportSubmitting || mode === "SAMPLE" || snapshot.frame_source === "SYNTHETIC_SAMPLE",
                      onClick: () => void handleDownloadExperimentZip(),
                      className: "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded text-[11px] font-semibold bg-[#3DE8E5]/20 hover:bg-[#3DE8E5]/30 text-[#3DE8E5] border border-[#3DE8E5]/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
                      children: exportSubmitting ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
                        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RefreshCw, { className: "w-3 h-3 animate-spin" }),
                        " \u6253\u5305\u4E0B\u8F7D\u4E2D..."
                      ] }) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
                        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Download, { className: "w-3 h-3" }),
                        " \u5BFC\u51FA\u5B8C\u6574 ZIP \u5B9E\u9A8C\u5305"
                      ] })
                    }
                  )
                ] })
              ]
            }
          )
        }
      )
    ] });
  }

  // web/console/main.tsx
  var import_jsx_runtime2 = __toESM(require_jsx_runtime());
  var container = document.getElementById("root");
  if (!container) {
    throw new Error("Root element #root not found");
  }
  (0, import_client.createRoot)(container).render(
    /* @__PURE__ */ (0, import_jsx_runtime2.jsx)(import_react4.default.StrictMode, { children: /* @__PURE__ */ (0, import_jsx_runtime2.jsx)(App, {}) })
  );
})();
/*! Bundled license information:

react/cjs/react.production.min.js:
  (**
   * @license React
   * react.production.min.js
   *
   * Copyright (c) Facebook, Inc. and its affiliates.
   *
   * This source code is licensed under the MIT license found in the
   * LICENSE file in the root directory of this source tree.
   *)

scheduler/cjs/scheduler.production.min.js:
  (**
   * @license React
   * scheduler.production.min.js
   *
   * Copyright (c) Facebook, Inc. and its affiliates.
   *
   * This source code is licensed under the MIT license found in the
   * LICENSE file in the root directory of this source tree.
   *)

react-dom/cjs/react-dom.production.min.js:
  (**
   * @license React
   * react-dom.production.min.js
   *
   * Copyright (c) Facebook, Inc. and its affiliates.
   *
   * This source code is licensed under the MIT license found in the
   * LICENSE file in the root directory of this source tree.
   *)

react/cjs/react-jsx-runtime.production.min.js:
  (**
   * @license React
   * react-jsx-runtime.production.min.js
   *
   * Copyright (c) Facebook, Inc. and its affiliates.
   *
   * This source code is licensed under the MIT license found in the
   * LICENSE file in the root directory of this source tree.
   *)

lucide-react/dist/esm/shared/src/utils.js:
lucide-react/dist/esm/defaultAttributes.js:
lucide-react/dist/esm/Icon.js:
lucide-react/dist/esm/createLucideIcon.js:
lucide-react/dist/esm/icons/activity.js:
lucide-react/dist/esm/icons/bot.js:
lucide-react/dist/esm/icons/camera.js:
lucide-react/dist/esm/icons/chevron-down.js:
lucide-react/dist/esm/icons/chevron-right.js:
lucide-react/dist/esm/icons/circle-check.js:
lucide-react/dist/esm/icons/circle-x.js:
lucide-react/dist/esm/icons/clock.js:
lucide-react/dist/esm/icons/cpu.js:
lucide-react/dist/esm/icons/database.js:
lucide-react/dist/esm/icons/download.js:
lucide-react/dist/esm/icons/file-code-2.js:
lucide-react/dist/esm/icons/film.js:
lucide-react/dist/esm/icons/folder-open.js:
lucide-react/dist/esm/icons/git-branch.js:
lucide-react/dist/esm/icons/grid-3x3.js:
lucide-react/dist/esm/icons/history.js:
lucide-react/dist/esm/icons/layers.js:
lucide-react/dist/esm/icons/lock.js:
lucide-react/dist/esm/icons/monitor.js:
lucide-react/dist/esm/icons/play.js:
lucide-react/dist/esm/icons/radio.js:
lucide-react/dist/esm/icons/refresh-cw.js:
lucide-react/dist/esm/icons/rotate-ccw.js:
lucide-react/dist/esm/icons/scan.js:
lucide-react/dist/esm/icons/settings.js:
lucide-react/dist/esm/icons/shield-alert.js:
lucide-react/dist/esm/icons/shield-check.js:
lucide-react/dist/esm/icons/square.js:
lucide-react/dist/esm/icons/triangle-alert.js:
lucide-react/dist/esm/icons/upload.js:
lucide-react/dist/esm/icons/wifi-off.js:
lucide-react/dist/esm/icons/x.js:
lucide-react/dist/esm/lucide-react.js:
  (**
   * @license lucide-react v0.468.0 - ISC
   *
   * This source code is licensed under the ISC license.
   * See the LICENSE file in the root directory of this source tree.
   *)
*/
