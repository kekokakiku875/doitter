$(function(){
 console.log("あいうえお")
    $('.good-btn').click(function(e){
        e.stopPropagation();
        console.log("かきくけこ")
        var $this = $(this);
        var number = $this.data('tweet_id')
        var data = JSON.stringify({"tweet_id":number});
        console.log(data)
        $.ajax({
            type: 'POST',
            url: '/good',
            data: data,
            contentType:'application/json',
        }).done(function(data){
            console.log('成功')
            console.log(JSON.parse(data["values"]))
            var change = JSON.parse(data["values"])
            $("#"+number).html(change["tweet_good"])
            $this.toggleClass('good');
        }).fail(function(msg) {
            console.log('Ajax Error');
        });
    });
});

$(function(){
 console.log("さしすせそ")
    $('.post-delete').click(function(e){
        e.stopPropagation();
        console.log("なにぬねの")
        var $this = $(this);
        var number = $this.data('tweet_id')
        var data = JSON.stringify({"tweet_id":number});
        console.log(data)
        $.ajax({
            type: 'POST',
            url: '/post/delete',
            data: data,
            contentType:'application/json',
        }).done(function(data){
            console.log('成功')
            $("#"+number+"del").toggleClass('none');
        }).fail(function(msg) {
            console.log('Ajax Error');
        });
    });
});