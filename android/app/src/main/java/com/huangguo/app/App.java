package com.huangguo.app;

import android.app.Application;
import android.content.Context;

public class App extends Application {
    public static Context CTX;

    @Override
    public void onCreate() {
        super.onCreate();
        CTX = getApplicationContext();
    }
}
