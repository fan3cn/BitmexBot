pid=`ps aux | grep "python3 main.py" | grep -v "grep" | awk '{if(NR == 1)print $2}'`
if [ -z "$pid" ]; then
    echo "Bitmex bot is not running, exit."
    exit 1
fi
echo $pid
kill -15 $pid
sleep 5
kill -15 $pid
echo "Bitmex bot stopped running."

