package com.huangguo.app;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import java.util.List;

public class EpisodeAdapter extends RecyclerView.Adapter<EpisodeAdapter.VH> {

    public interface Callback {
        void onPlay(int pos);

        void onDownload(int pos);
    }

    private final List<Site.Episode> data;
    private final Callback cb;

    public EpisodeAdapter(List<Site.Episode> data, Callback cb) {
        this.data = data;
        this.cb = cb;
    }

    @NonNull
    @Override
    public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View v = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_episode, parent, false);
        return new VH(v);
    }

    @Override
    public void onBindViewHolder(@NonNull VH h, int pos) {
        Site.Episode e = data.get(pos);
        h.btnEp.setText(e.name);
        h.btnEp.setOnClickListener(v -> {
            if (cb != null) cb.onPlay(pos);
        });
        h.btnEp.setOnLongClickListener(v -> {
            if (cb != null) {
                cb.onDownload(pos);
                return true;
            }
            return false;
        });
    }

    @Override
    public int getItemCount() {
        return data.size();
    }

    static class VH extends RecyclerView.ViewHolder {
        Button btnEp;

        VH(View v) {
            super(v);
            btnEp = v.findViewById(R.id.btnEp);
        }
    }
}
