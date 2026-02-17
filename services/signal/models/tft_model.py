import torch
import torch.nn as nn
import math

class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_len=5000):
        super(PositionalEncoding, self).__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)
        self.register_buffer('pe', pe)

    def forward(self, x):
        return x + self.pe[:x.size(0), :]

class TFTModel(nn.Module):
    """
    Simplified Transformer for Time Series Forecasting (MVP for TFT).
    Uses standard TransformerEncoder.
    """
    def __init__(self, input_size=14, d_model=64, nhead=4, num_layers=2, output_horizon=5, dropout=0.1):
        super(TFTModel, self).__init__()
        
        self.input_embedding = nn.Linear(input_size, d_model)
        self.pos_encoder = PositionalEncoding(d_model)
        
        encoder_layers = nn.TransformerEncoderLayer(d_model, nhead, dim_feedforward=d_model*4, dropout=dropout)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layers, num_layers)
        
        self.decoder = nn.Linear(d_model, output_horizon)
        self.d_model = d_model

    def forward(self, x):
        # x: [batch, seq_len, input_size]
        # Transformer expects [seq_len, batch, d_model]
        
        x = self.input_embedding(x) # [batch, seq_len, d_model]
        x = x.permute(1, 0, 2)      # [seq_len, batch, d_model]
        
        x = self.pos_encoder(x)
        output = self.transformer_encoder(x) # [seq_len, batch, d_model]
        
        # We take the output of the last time step for forecasting
        last_step_output = output[-1, :, :] # [batch, d_model]
        
        prediction = self.decoder(last_step_output) # [batch, output_horizon]
        return prediction
