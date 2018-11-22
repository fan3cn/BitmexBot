echo "Stopping..."
sh stop.sh
echo "Starting..."
nohup python3 main.py &
tail -f nohup.out
