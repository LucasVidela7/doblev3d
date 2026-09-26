package ar.com.doblev3d.gestion;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Insets;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.MimeTypeMap;
import android.webkit.SafeBrowsingResponse;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.ProgressBar;
import android.widget.Toast;

import java.net.URISyntaxException;
import java.util.Locale;

public class MainActivity extends Activity {
    private static final String START_URL = "https://doblev3d.com.ar/gestion/";
    private static final int FILE_CHOOSER_REQUEST = 1001;

    private WebView webView;
    private ProgressBar progressBar;
    private ValueCallback<Uri[]> fileCallback;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        FrameLayout root = new FrameLayout(this);
        webView = new WebView(this);
        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(100);

        // Android 15 puede dibujar la Activity detrás de las barras del sistema.
        // Aplicamos los insets reales para que Gestión nunca quede debajo de
        // la hora, señal, batería ni del área de gestos inferior.
        root.setOnApplyWindowInsetsListener((view, windowInsets) -> {
            Insets statusBars = windowInsets.getInsets(WindowInsets.Type.statusBars());
            Insets navigationBars = windowInsets.getInsets(WindowInsets.Type.navigationBars());
            view.setPadding(0, statusBars.top, 0, navigationBars.bottom);
            return windowInsets;
        });

        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));

        FrameLayout.LayoutParams progressParams = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(3)
        );
        progressParams.gravity = Gravity.TOP;
        root.addView(progressBar, progressParams);
        setContentView(root);

        configureWebView();

        if (savedInstanceState == null) {
            webView.loadUrl(START_URL);
        } else {
            webView.restoreState(savedInstanceState);
        }
    }

    private void configureWebView() {
        WebView.setWebContentsDebuggingEnabled(false);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        settings.setGeolocationEnabled(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setSupportMultipleWindows(true);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setUserAgentString(settings.getUserAgentString() + " DobleVGestion/1.0");

        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, false);

        webView.setWebViewClient(new GestionWebViewClient());
        webView.setWebChromeClient(new GestionChromeClient());
        webView.setDownloadListener(new GestionDownloadListener());
    }

    private boolean isInternal(Uri uri) {
        if (uri == null || uri.getHost() == null) return false;
        String host = uri.getHost().toLowerCase(Locale.ROOT);
        return host.equals("doblev3d.com.ar")
                || host.equals("www.doblev3d.com.ar")
                || host.equals("doblev3d-production.up.railway.app");
    }

    private boolean openExternal(String rawUrl) {
        if (rawUrl == null || rawUrl.trim().isEmpty()) return false;

        try {
            if (rawUrl.startsWith("intent:")) {
                Intent intent = Intent.parseUri(rawUrl, Intent.URI_INTENT_SCHEME);
                try {
                    startActivity(intent);
                    return true;
                } catch (ActivityNotFoundException missingApp) {
                    String fallback = intent.getStringExtra("browser_fallback_url");
                    if (fallback != null) {
                        startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(fallback)));
                        return true;
                    }
                    return false;
                }
            }

            Uri uri = Uri.parse(rawUrl);
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);

            if (("https".equals(scheme) || "http".equals(scheme)) && isInternal(uri)) {
                webView.loadUrl(rawUrl);
                return true;
            }

            if ("https".equals(scheme)
                    || "http".equals(scheme)
                    || "mailto".equals(scheme)
                    || "tel".equals(scheme)
                    || "sms".equals(scheme)
                    || "geo".equals(scheme)
                    || "whatsapp".equals(scheme)) {
                startActivity(new Intent(Intent.ACTION_VIEW, uri));
                return true;
            }
        } catch (Exception ex) {
            Toast.makeText(this, "No se pudo abrir el enlace.", Toast.LENGTH_SHORT).show();
        }

        return false;
    }

    private void showOfflinePage() {
        String html = "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
                + "<style>body{font-family:Arial,sans-serif;background:#f4f5f7;color:#24272b;margin:0;"
                + "display:grid;place-items:center;min-height:100vh;padding:24px;box-sizing:border-box}"
                + ".c{max-width:420px;text-align:center;background:#fff;border:1px solid #e5e7eb;border-radius:18px;padding:28px}"
                + "h1{font-size:24px;margin:0 0 10px}p{color:#73777f;line-height:1.45;margin:0 0 20px}"
                + "a{display:inline-flex;min-height:46px;align-items:center;justify-content:center;padding:0 18px;"
                + "border-radius:12px;background:#24272b;color:#fff;text-decoration:none;font-weight:800}</style></head>"
                + "<body><div class='c'><h1>Sin conexión</h1><p>No se pudo conectar con Doble V Gestión. "
                + "Revisá tu conexión y volvé a intentar.</p><a href='" + START_URL + "'>Reintentar</a></div></body></html>";
        webView.loadDataWithBaseURL(START_URL, html, "text/html", "UTF-8", null);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        webView.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.stopLoading();
            webView.setWebChromeClient(null);
            webView.setWebViewClient(null);
            webView.destroy();
        }
        super.onDestroy();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == FILE_CHOOSER_REQUEST) {
            if (fileCallback != null) {
                Uri[] result = null;
                if (resultCode == RESULT_OK && data != null) {
                    if (data.getClipData() != null) {
                        int count = data.getClipData().getItemCount();
                        result = new Uri[count];
                        for (int i = 0; i < count; i++) {
                            result[i] = data.getClipData().getItemAt(i).getUri();
                        }
                    } else if (data.getData() != null) {
                        result = new Uri[]{data.getData()};
                    }
                }
                fileCallback.onReceiveValue(result);
                fileCallback = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private class GestionWebViewClient extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri uri = request.getUrl();
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);

            if (("https".equals(scheme) || "http".equals(scheme)) && isInternal(uri)) {
                return false;
            }
            if ("about".equals(scheme) || "data".equals(scheme) || "blob".equals(scheme)) {
                return false;
            }
            return openExternal(uri.toString());
        }

        @Override
        public void onPageStarted(WebView view, String url, Bitmap favicon) {
            progressBar.setVisibility(View.VISIBLE);
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            CookieManager.getInstance().flush();
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request.isForMainFrame()) {
                showOfflinePage();
            }
        }

        @Override
        public void onSafeBrowsingHit(WebView view, WebResourceRequest request, int threatType, SafeBrowsingResponse callback) {
            callback.backToSafety(true);
        }
    }

    private class GestionChromeClient extends WebChromeClient {
        @Override
        public void onProgressChanged(WebView view, int newProgress) {
            progressBar.setProgress(newProgress);
            progressBar.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
        }

        @Override
        public boolean onShowFileChooser(
                WebView webView,
                ValueCallback<Uri[]> filePathCallback,
                FileChooserParams fileChooserParams
        ) {
            if (fileCallback != null) {
                fileCallback.onReceiveValue(null);
            }
            fileCallback = filePathCallback;

            Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            intent.setType("*/*");
            intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, fileChooserParams.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);

            try {
                startActivityForResult(Intent.createChooser(intent, "Seleccionar archivo"), FILE_CHOOSER_REQUEST);
                return true;
            } catch (ActivityNotFoundException ex) {
                fileCallback = null;
                Toast.makeText(MainActivity.this, "No hay un selector de archivos disponible.", Toast.LENGTH_SHORT).show();
                return false;
            }
        }

        @Override
        public boolean onCreateWindow(WebView view, boolean isDialog, boolean isUserGesture, android.os.Message resultMsg) {
            WebView popup = new WebView(MainActivity.this);
            popup.setWebViewClient(new WebViewClient() {
                @Override
                public boolean shouldOverrideUrlLoading(WebView child, WebResourceRequest request) {
                    Uri uri = request.getUrl();
                    if (isInternal(uri)) {
                        MainActivity.this.webView.loadUrl(uri.toString());
                    } else {
                        openExternal(uri.toString());
                    }
                    child.destroy();
                    return true;
                }
            });

            WebView.WebViewTransport transport = (WebView.WebViewTransport) resultMsg.obj;
            transport.setWebView(popup);
            resultMsg.sendToTarget();
            return true;
        }
    }

    private class GestionDownloadListener implements DownloadListener {
        @Override
        public void onDownloadStart(String url, String userAgent, String contentDisposition, String mimeType, long contentLength) {
            try {
                DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
                String cookies = CookieManager.getInstance().getCookie(url);
                if (cookies != null) request.addRequestHeader("Cookie", cookies);
                if (userAgent != null) request.addRequestHeader("User-Agent", userAgent);
                request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                request.setAllowedOverMetered(true);
                request.setAllowedOverRoaming(false);

                String fileName = android.webkit.URLUtil.guessFileName(url, contentDisposition, mimeType);
                request.setTitle(fileName);

                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
                    request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName);
                } else {
                    request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName);
                }

                DownloadManager manager = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                manager.enqueue(request);
                Toast.makeText(MainActivity.this, "Descarga iniciada.", Toast.LENGTH_SHORT).show();
            } catch (Exception ex) {
                Toast.makeText(MainActivity.this, "No se pudo iniciar la descarga.", Toast.LENGTH_SHORT).show();
                openExternal(url);
            }
        }
    }
}
