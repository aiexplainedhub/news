<?php
/**
 * Plugin Name: Yoast REST Bridge
 * Description: Expose key Yoast SEO meta keys for REST writes.
 */

add_action('init', function () {
    $post_types = get_post_types(['public' => true], 'names');

    $yoast_keys = [
        '_yoast_wpseo_focuskw'   => 'string',
        '_yoast_wpseo_metadesc'  => 'string',
        '_yoast_wpseo_title'     => 'string',
        '_yoast_wpseo_canonical' => 'string',
    ];

    foreach ($post_types as $type) {
        foreach ($yoast_keys as $key => $type_def) {
            register_post_meta($type, $key, [
                'type'          => $type_def,
                'single'        => true,
                'show_in_rest'  => true,
                'auth_callback' => function() { return current_user_can('edit_posts'); },
            ]);
        }
    }
});
