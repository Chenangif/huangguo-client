package com.huangguo.app;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import java.util.List;

public class CardAdapter extends RecyclerView.Adapter<CardAdapter.VH> {

    public interface OnCardClick {
        void onClick(Site.Card c);
    }

    public interface OnCardLongClick {
        boolean onLongClick(Site.Card c);
    }

    private final List<Site.Card> data;
    private final OnCardClick cb;
    private final OnCardLongClick longCb;

    public CardAdapter(List<Site.Card> data, OnCardClick cb) {
        this(data, cb, null);
    }

    public CardAdapter(List<Site.Card> data, OnCardClick cb, OnCardLongClick longCb) {
        this.data = data;
        this.cb = cb;
        this.longCb = longCb;
    }

    @NonNull
    @Override
    public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View v = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_card, parent, false);
        return new VH(v);
    }

    @Override
    public void onBindViewHolder(@NonNull VH h, int pos) {
        Site.Card c = data.get(pos);
        h.tvTitle.setText(c.name);
        h.tvRem.setText(c.remarks == null ? "" : c.remarks);
        CoverLoader.load(h.iv.getContext(), c.pic, h.iv);
        h.itemView.setOnClickListener(v -> {
            if (cb != null) cb.onClick(c);
        });
        h.itemView.setOnLongClickListener(v -> longCb != null && longCb.onLongClick(c));
    }

    @Override
    public int getItemCount() {
        return data.size();
    }

    static class VH extends RecyclerView.ViewHolder {
        ImageView iv;
        TextView tvTitle, tvRem;

        VH(View v) {
            super(v);
            iv = v.findViewById(R.id.ivCover);
            tvTitle = v.findViewById(R.id.tvTitle);
            tvRem = v.findViewById(R.id.tvRem);
        }
    }
}
