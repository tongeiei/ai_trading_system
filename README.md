# ai_trading_system

view ui on local
ssh -i ~/.ssh/oracle_trading_vps.key -N -L 8501:127.0.0.1:8501 ubuntu@134.185.81.78  

ssh ubuntu@134.185.81.78   'cd ai_trading_system && git log --oneline -3 && systemctl status signal-cycle.timer && journalctl -u signal-cycle -n 50'